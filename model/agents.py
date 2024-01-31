# Importing necessary libraries
import random
import numpy as np
from mesa import Agent
from shapely.geometry import Point
from shapely import contains_xy

# Import functions from functions.py
from functions import generate_random_location_within_map_domain, get_flood_depth, calculate_basic_flood_damage, floodplain_multipolygon, load_flood_map, expected_utility_prospect_theory, risk_perception_bayesian_PT


# Define the Households agent class
class Households(Agent):
    """
    An agent representing a household in the model.
    Each household has a flood depth attribute which is randomly assigned for demonstration purposes.
    In a real scenario, this would be based on actual geographical data or more complex logic.
    """

    def __init__(self, unique_id, model, savings_range):
        super().__init__(unique_id, model)
        
        self.is_adapted = False  # Initial adaptation status set to False
        self.adapted_at_t = None  # Initialize the time step at which the agent adapts to None
        
        self.savings_range = savings_range  # Add savings attribute
    
        # Assign agent to an income category based on the income distribution in Houston #TODO: Source
        self.income_category = random.choices(['low', 'middle', 'high'], weights=[0.34, 0.29, 0.37])[0]
    
        # Assign income-specific attributes based on the category
        if self.income_category == 'low':
            self.savings = random.randint(self.savings_range[0][0], self.savings_range[0][1])
            # additional attributes for low income households if needed
        elif self.income_category == 'middle':
            self.savings = random.randint(self.savings_range[1][0], self.savings_range[1][1])
            # additional attributes for middle income households if needed
        elif self.income_category == 'high':
            self.savings = random.randint(self.savings_range[2][0], self.savings_range[2][1])
            # additional attributes for high income households if needed

        #TODO: integrate housing size for each income category? this should be connected to the damage function

        # getting flood map values
        # Get a random location on the map
        loc_x, loc_y = generate_random_location_within_map_domain()
        self.location = Point(loc_x, loc_y)

        # Check whether the location is within floodplain
        self.in_floodplain = False
        if contains_xy(geom=floodplain_multipolygon, x=self.location.x, y=self.location.y):
            self.in_floodplain = True

        # List of flood map choices
        flood_map_choices = ['harvey', '100yr', '500yr']

        # List to store flood_depth_estimated for each choice
        self.flood_depth_estimated_list = []

        # Calculate flood_depth_estimated for each choice
        for choice in flood_map_choices:
            # Load the flood map
            flood_map = load_flood_map(choice)
            # Update the band
            model.band_flood_img = flood_map.read(1)
            # Get the estimated flood depth at those coordinates
            self.flood_depth_estimated = get_flood_depth(corresponding_map=flood_map, location=self.location, band=model.band_flood_img)
  
            # Flood depth can be negative if the location is at a high elevation
            # handle negative values of flood depth
            if self.flood_depth_estimated < 0:
                self.flood_depth_estimated = 0
            self.flood_depth_estimated_list.append(self.flood_depth_estimated)

        # Add an additional last list element with the value of 0 for the flood depth in the case of no flooding
        self.flood_depth_estimated_list.append(0)
        
        # Calculate the estimated flood damage given the estimated flood depth. Flood damage is a factor between 0 and 1
        self.flood_damage_estimated_list = []
        for flood_depth in self.flood_depth_estimated_list:
            self.flood_damage_estimated_list.append(calculate_basic_flood_damage(flood_depth=flood_depth))
        
        # Create a list with percived flood risk
        self.flood_risk = [0.05, 0.15, 0.3, 0.5] # TODO: what are the assumptions behind this?
        
        # Cost of adaption measures to lift to 1.3 m above ground level
        self.cost_measure = 35000

        # Add an attribute for the actual flood depth. This is set to zero at the beginning of the simulation since there is not flood yet
        # and will update its value when there is a shock (i.e., actual flood). Shock happens at some point during the simulation
        self.flood_depth_actual = 0
        
        #calculate the actual flood damage given the actual flood depth. Flood damage is a factor between 0 and 1
        self.flood_damage_actual = calculate_basic_flood_damage(flood_depth=self.flood_depth_actual)
        
        # the individual risk perception (RP) at time (t) (= RPt) is a value between 0 and 1
        # The risk perception RPt of individuals canlead to a positive or negative misjudgment of theprobability of a flood by a factor of 10 from the objective probability flood_risk
        self.RPt = np.random.normal(0.5, 0.5)
        # Ensure RPt is within [0, 1]
        self.RPt = max(0, min(self.RPt, 1))
        
        # initialization of the risk perception at time (t-1) (= RPt_1) to store the risk perception of the previous time step
        self.RPt_1 = None
        
        self.expected_utility_measure = 0 # Initialize the expected utility for adaptation=True
        self.expected_utility_nomeasure = 0 # Initialize the expected utility for adaptation=False
    
    # Function to count friends who can be influencial.
    def count_friends(self, radius):
        """Count the number of neighbors within a given radius (number of edges away). This is social relation and not spatial"""
        friends = self.model.grid.get_neighborhood(self.pos, include_center=False, radius=radius)
        return len(friends)

    def step(self):
        
        self.RPt_1 = self.RPt # store the risk perception of the previous time step
        
        # count neighbors within a radius of 1
        if self.count_friends(radius=1) > 0:
            I_social = np.mean([neighbor.RPt for neighbor in self.model.grid.get_neighbors(self.pos)]) # the social influence is the average risk perception of the neighbors
        else:
            I_social = 1 # according to Haer et al. (2017) the social influence is considered 1.0 if its closest to their own risk perception, i.e., no social influence
        
        self.RPt = risk_perception_bayesian_PT(RPt_1=self.RPt_1, I_social= I_social, I_media=self.model.government.information, flood_occurs=self.model.flood_occurs)
        
        # Expected utility based on the prospect theory, Source:
        # Haer, T., Botzen, W. J. W., de Moel, H., & Aerts, J. C. J. H. (2017).
        # Integrating Household Risk Mitigation Behavior in Flood Risk Analysis: An Agent-Based Model Approach.
        # Risk Analysis, 37(10), 1977–1992. https://doi.org/10.1111/risa.12740
        
        # Sum the expected utilities for each flood risk and perceived flood damage to get the total expected utility for action=True and action=False
        for risk_of_flood, perceived_flood_damage in zip(self.flood_risk, self.flood_damage_estimated_list):
            # Calculate the expected utility for adaptation=True
            utility_adaptation_true = expected_utility_prospect_theory(risk_of_flood=risk_of_flood,
                                                                       percieved_flood_damage=perceived_flood_damage,
                                                                       RPt=self.RPt,
                                                                       cost_of_measure=self.cost_measure,
                                                                       subsidie=self.model.government.subsidies,
                                                                       action=True
                                                                       )
            # Add the result to the sum for adaptation=True
            self.expected_utility_measure += utility_adaptation_true

            # Calculate the expected utility for adaptation=False
            utility_adaptation_false = expected_utility_prospect_theory(risk_of_flood=risk_of_flood,
                                                                        percieved_flood_damage=perceived_flood_damage,
                                                                        RPt=self.RPt,
                                                                        cost_of_measure=self.cost_measure,
                                                                        subsidie=self.model.government.subsidies,
                                                                        action=False
                                                                        )
            # Add the result to the sum for adaptation=False
            self.expected_utility_nomeasure += utility_adaptation_false
        
        # Threshold of minimum savings housholds still have after taking adaption measures
        savings_threshold = 5000
        
        # Logic for adaptation based on estimated flood damage and a random chance.
        # These conditions are examples and should be refined for real-world applications.
        if self.expected_utility_measure > self.expected_utility_nomeasure and self.savings > (self.cost_measure - self.model.government.subsidies + savings_threshold):
            self.is_adapted = True  # Agent adapts to flooding
            self.savings = self.savings - self.cost_measure  # Agent pays for adaptation measures
            self.adapted_at_t = self.model.schedule.steps  # Set the time step at which the agent adapts
        
        # Logic for adaptation based on neighbors who have adapted and a random chance
        # Iterate over the neighbors
        #for neighbor in self.model.grid.get_neighbors(self.pos):
            #TODO: Interestingly,information can spread not only through established social network connections but also from
            # spatially proximate households, even if they are not directly connected in the social network
            
            # If the neighbor is adapted and there is a 1% chance of adapting and the savings are enough to pay for the adaptation measure
            #if neighbor.is_adapted and random.random() < 0.01 and self.savings > (self.cost_measure + savings_threshold):
                # Set self to adapted
               # self.is_adapted = True
                # Iteration is not stopped with "break" to increase likelihood with more neighbors
        
        # Multiply the savings with a random factor between 0.95 and 1.15 to simulate savings and expenses of the household
        self.savings = self.savings * random.uniform(0.95, 1.05)
        
        
        
        
# Define the Government agent class
class Government(Agent):
    """
    The government agent class represents the government in the model.
    The government has two policy instruments: subsidies and information campaign.
   
    """
    def __init__(self, unique_id, model, subsidie_level, information_bias):
        super().__init__(unique_id, model)
        
        self.spendings = 0 # Add spendings attribute, this will keep track of the spendings of the government
        
        # subsidies polyicy instrument
        self.subsidies = subsidie_level # in USD
        
        # information campaign poyicy instrument
        self.information = 0.5 + information_bias # the information campaign is a value between 0 and 1
        
        self.previous_adapted_households = 0 # information/memory the government agent has about the number of adapted households in the previous time step

    def step(self):
        
        # government pays for the information campaign per 1/4 year (1 timestep)
        if self.information != 0.5:
            factor = abs(0.5 - self.information)/0.1 # the factor is between 0 and 5
            self.spendings += 2000 * factor # the spendings are positive but should be interpreted as negative values (in USD)
        
        if self.subsidies > 0:
            total_adapted_households = sum([1 for agent in self.model.schedule.agents if agent.is_adapted == True])
            num_newly_adapted_households = total_adapted_households - self.previous_adapted_households
            self.spendings += self.subsidies * num_newly_adapted_households
            self.previous_adapted_households = total_adapted_households
            
        pass

# More agent classes can be added here, e.g. for insurance agents.
# This is not mandatory. I think we should leave it for now. We can add it later if we have time.
