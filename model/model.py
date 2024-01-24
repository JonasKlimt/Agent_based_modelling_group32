# Importing necessary libraries
import networkx as nx
from mesa import Model, Agent
from mesa.time import RandomActivation
from mesa.space import NetworkGrid
from mesa.datacollection import DataCollector
import geopandas as gpd
import rasterio as rs
import matplotlib.pyplot as plt
import random

# Import the agent class(es) from agents.py
from agents import Households
from agents import Government

# Import functions from functions.py
from functions import get_flood_map_data, calculate_basic_flood_damage, calculate_adapted_flood_damage, get_flood_depth, load_flood_map
from functions import map_domain_gdf, floodplain_gdf


# Define the AdaptationModel class
class AdaptationModel(Model):
    """
    The main model running the simulation. It sets up the network of household agents,
    simulates their behavior, and collects data. The network type can be adjusted based on study requirements.
    """

    def __init__(self, 
                 seed = None,
                 number_of_households = 25, # number of household agents
                 # Simplified argument for choosing flood map. Can currently be "harvey", "100yr", or "500yr".
                 flood_map_choice='harvey',
                 # ### network related parameters ###
                 # The social network structure that is used.
                 # Can currently be "erdos_renyi", "barabasi_albert", "watts_strogatz", or "no_network"
                 network = 'watts_strogatz',
                 # likeliness of edge being created between two nodes
                 probability_of_network_connection = 0.4,
                 # number of edges for BA network
                 number_of_edges = 3,
                 # number of nearest neighbours for WS social network
                 number_of_nearest_neighbours = 5,
                 # subsidie level the government provides
                 subsidie_level = 0.0,
                 # information bias of the government
                 information_bias = 0.0,
                 ):
        
        super().__init__(seed = seed)
        
        # defining the variables and setting the values
        self.number_of_households = number_of_households  # Total number of household agents
        self.seed = seed

        # network
        self.network = network # Type of network to be created
        self.probability_of_network_connection = probability_of_network_connection
        self.number_of_edges = number_of_edges
        self.number_of_nearest_neighbours = number_of_nearest_neighbours

        # generating the graph according to the network used and the network parameters specified
        self.G = self.initialize_network()
        # create grid out of network graph
        self.grid = NetworkGrid(self.G)

        # Create attribute that is the flood map choice
        self.flood_map_choice = flood_map_choice

        # Initialize maps
        self.initialize_maps(flood_map_choice)

        # set schedule for agents
        self.schedule = RandomActivation(self)  # Schedule for activating agents
        
        # Create a Government agent and assign it to an attribute
        self.government = Government(unique_id=50, model=self, subsidie_level=subsidie_level, information_bias=information_bias)
        
        # Define the savings levels
        savings_levels = [(0, 20000), (20000, 70000), (70000, 250000)]

        # Create households through initiating a household on each node of the network graph
        for i, node in enumerate(self.G.nodes()):
            # Pass the entire savings_levels list to the Household
            household = Households(unique_id=i, model=self, savings_range=savings_levels)
            
            # Add the household to the schedule and place it on the grid
            self.schedule.add(household)
            self.grid.place_agent(agent=household, node_id=node)
            
        # Define when flood occurs (in steps)
        self.flood_occurs = 70

        # Data collection setup to collect data
        model_metrics = {
            "Total_adapted_households": self.total_adapted_households,
            "GovernmentSpendings": lambda m: m.government.spendings,
            # ... other reporters ...
            # TODO: add more model metrics here?
        }
        
        agent_metrics = {
                        "FloodDepthEstimated": "flood_depth_estimated_list",
                        "FloodDamageEstimated" : "flood_damage_estimated_list",
                        "ExpectedUtilityAdaption" : "expected_utility_measure",
                        "ExpectedUtilityNoAdaption" : "expected_utility_nomeasure",
                        "RiskPerception" : "RPt",
                        "PriorRiskPerception" : "RPt_1",
                        "FloodDepthActual": "flood_depth_actual",
                        "FloodDamageActual" : "flood_damage_actual",
                        "IsAdapted": "is_adapted",
                        "FriendsCount": lambda a: a.count_friends(radius=1),
                        "Location":"location",
                        "Savings":"savings",
                        "IncomeCategory":"income_category",
                        # ... other reporters ...
                        # TODO: add more agent metrics here?
                        }
            
        #set up the data collector 
        self.datacollector = DataCollector(
            model_reporters=model_metrics, 
            agent_reporters=agent_metrics
        )
            

    def initialize_network(self):
        """
        Initialize and return the social network graph based on the provided network type using pattern matching.
        """
        if self.network == 'erdos_renyi':
            return nx.erdos_renyi_graph(n=self.number_of_households,
                                        p=self.number_of_nearest_neighbours / self.number_of_households,
                                        seed=self.seed)
        elif self.network == 'barabasi_albert':
            return nx.barabasi_albert_graph(n=self.number_of_households,
                                            m=self.number_of_edges,
                                            seed=self.seed)
        elif self.network == 'watts_strogatz':
            return nx.watts_strogatz_graph(n=self.number_of_households,
                                        k=self.number_of_nearest_neighbours,
                                        p=self.probability_of_network_connection,
                                        seed=self.seed)
        elif self.network == 'no_network':
            G = nx.Graph()
            G.add_nodes_from(range(self.number_of_households))
            return G
        else:
            raise ValueError(f"Unknown network type: '{self.network}'. "
                            f"Currently implemented network types are: "
                            f"'erdos_renyi', 'barabasi_albert', 'watts_strogatz', and 'no_network'")


    def initialize_maps(self, flood_map_choice):
        """
        Initialize and set up the flood map related data based on the provided flood map choice.
        """
        # Define paths to flood maps
        flood_map_paths = {
            'harvey': r'../input_data/floodmaps/Harvey_depth_meters.tif',
            '100yr': r'../input_data/floodmaps/100yr_storm_depth_meters.tif',
            '500yr': r'../input_data/floodmaps/500yr_storm_depth_meters.tif'  # Example path for 500yr flood map
        }

        # Throw a ValueError if the flood map choice is not in the dictionary
        if flood_map_choice not in flood_map_paths.keys():
            raise ValueError(f"Unknown flood map choice: '{flood_map_choice}'. "
                             f"Currently implemented choices are: {list(flood_map_paths.keys())}")

        # Choose the appropriate flood map based on the input choice
        flood_map_path = flood_map_paths[flood_map_choice]

        # Loading and setting up the flood map
        self.flood_map = rs.open(flood_map_path)
        self.band_flood_img, self.bound_left, self.bound_right, self.bound_top, self.bound_bottom = get_flood_map_data(
            self.flood_map)

    def total_adapted_households(self):
        """Return the total number of households that have adapted."""
        #BE CAREFUL THAT YOU MAY HAVE DIFFERENT AGENT TYPES SO YOU NEED TO FIRST CHECK IF THE AGENT IS ACTUALLY A HOUSEHOLD AGENT USING "ISINSTANCE"
        adapted_count = sum([1 for agent in self.schedule.agents if isinstance(agent, Households) and agent.is_adapted])
        return adapted_count

    def plot_model_domain_with_agents(self):
        fig, ax = plt.subplots()
        # Plot the model domain
        map_domain_gdf.plot(ax=ax, color='lightgrey')
        # Plot the floodplain
        floodplain_gdf.plot(ax=ax, color='lightblue', edgecolor='k', alpha=0.5)

        # Collect agent locations and statuses
        for agent in self.schedule.agents:
            color = 'blue' if agent.is_adapted else 'red'
            ax.scatter(agent.location.x, agent.location.y, color=color, s=10, label=color.capitalize() if not ax.collections else "")
            ax.annotate(str(agent.unique_id), (agent.location.x, agent.location.y), textcoords="offset points", xytext=(0,1), ha='center', fontsize=9)
        # Create legend with unique entries
        handles, labels = ax.get_legend_handles_labels()
        by_label = dict(zip(labels, handles))
        ax.legend(by_label.values(), by_label.keys(), title="Red: not adapted, Blue: adapted")

        # Customize plot with titles and labels
        plt.title(f'Model Domain with Agents at Step {self.schedule.steps}')
        plt.xlabel('Longitude')
        plt.ylabel('Latitude')
        plt.show()

    def step(self):
        """
        introducing a shock: 
        at time step 5, there will be a global flooding.
        This will result in actual flood depth. Here, we assume it is a random number
        between 0.5 and 1.2 of the estimated flood depth. In your model, you can replace this
        with a more sound procedure (e.g., you can devide the floop map into zones and 
        assume local flooding instead of global flooding). The actual flood depth can be 
        estimated differently
        """
        
        if self.schedule.steps == self.flood_occurs:
            for agent in self.schedule.agents:
                # Calculate the actual flood depth as a random number between 0.5 and 1.2 times the estimated flood depth
                # agent.flood_depth_actual = random.uniform(0.5, 1.2) * agent.flood_depth_estimated
                
                # Calculate the actual flood depth based on the flood map
                agent.flood_depth_actual = get_flood_depth(corresponding_map=load_flood_map(self.flood_map_choice), location=agent.location, band=self.band_flood_img)
                # Flood depth can be negative if the location is at a high elevation
                # handle negative values of flood depth
                if agent.flood_depth_actual < 0:
                    agent.flood_depth_actual = 0
                    
                # IF statement to calculate flood damage depending on adaptation measures taken or not
                if agent.is_adapted:
                    # calculate the flood damage given the actual flood depth if household is adapted
                    agent.flood_damage_actual = calculate_adapted_flood_damage(agent.flood_depth_actual)
                else:
                    # calculate the flood damage given the actual flood depth if household is not adapted
                    agent.flood_damage_actual = calculate_basic_flood_damage(agent.flood_depth_actual)
                    
        # Collect data and advance the model by one step
        self.datacollector.collect(self)
        self.schedule.step()
