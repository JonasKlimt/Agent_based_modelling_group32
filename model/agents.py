# Importing necessary libraries
import random
from mesa import Agent
from shapely.geometry import Point
from shapely import contains_xy

# Import functions from functions.py
from functions import generate_random_location_within_map_domain, get_flood_depth, calculate_basic_flood_damage, floodplain_multipolygon


# Define the Households agent class
class Households(Agent):
    """
    An agent representing a household in the model.
    Each household has a flood depth attribute which is randomly assigned for demonstration purposes.
    In a real scenario, this would be based on actual geographical data or more complex logic.
    """

    def __init__(self, unique_id, model, savings):
        super().__init__(unique_id, model)
        self.is_adapted = False  # Initial adaptation status set to False
        
        self.savings = savings  # Add savings attribute

        # getting flood map values
        # Get a random location on the map
        loc_x, loc_y = generate_random_location_within_map_domain()
        self.location = Point(loc_x, loc_y)

        # Check whether the location is within floodplain
        self.in_floodplain = False
        if contains_xy(geom=floodplain_multipolygon, x=self.location.x, y=self.location.y):
            self.in_floodplain = True

        # Get the estimated flood depth at those coordinates. 
        # the estimated flood depth is calculated based on the flood map (i.e., past data) so this is not the actual flood depth
        # Flood depth can be negative if the location is at a high elevation
        self.flood_depth_estimated = get_flood_depth(corresponding_map=model.flood_map, location=self.location, band=model.band_flood_img)
        # handle negative values of flood depth
        if self.flood_depth_estimated < 0:
            self.flood_depth_estimated = 0
        
        # calculate the estimated flood damage given the estimated flood depth. Flood damage is a factor between 0 and 1
        self.flood_damage_estimated = calculate_basic_flood_damage(flood_depth=self.flood_depth_estimated)

        # Add an attribute for the actual flood depth. This is set to zero at the beginning of the simulation since there is not flood yet
        # and will update its value when there is a shock (i.e., actual flood). Shock happens at some point during the simulation
        self.flood_depth_actual = 0
        
        #calculate the actual flood damage given the actual flood depth. Flood damage is a factor between 0 and 1
        self.flood_damage_actual = calculate_basic_flood_damage(flood_depth=self.flood_depth_actual)
    
    # Function to count friends who can be influencial.
    def count_friends(self, radius):
        """Count the number of neighbors within a given radius (number of edges away). This is social relation and not spatial"""
        friends = self.model.grid.get_neighborhood(self.pos, include_center=False, radius=radius)
        return len(friends)

    def step(self):
        # Cost of adaption measures
        # cost_measure = 500 - Government.subsidies
        cost_measure = 500 - self.model.government.subsidies
        # Threshold of minimum savings housholds still have after taking adaption measures
        savings_threshold = 500
        
        # Logic for adaptation based on estimated flood damage and a random chance.
        # These conditions are examples and should be refined for real-world applications.
        if self.flood_damage_estimated > 0.15 and random.random() < 0.2 and self.savings > cost_measure + savings_threshold:
            self.is_adapted = True  # Agent adapts to flooding
            self.savings = self.savings - cost_measure  # Agent pays for adaptation measures
            
        # Multiply the savings with a random factor between 0.9 and 1.1 to simulate savings and expenses of the household
        self.savings = self.savings * random.uniform(0.9, 1.1)
            
        # TODO: Add more logic here. This is where the adaptation decision is made.
        # From the assignment:
            # households save money
            # households communictae with each other
            # households update their perception (this has to be introduced as well)
            # households recondiser their adaptation decision
            # households take adaption measures
            
            # all of the above must be modelled according to the prospect theory
        
# Define the Government agent class
class Government(Agent):
    """
    A government agent that currently doesn't perform any actions.
    """
    def __init__(self, unique_id, model):
        super().__init__(unique_id, model)
        self.subsidies = 300 # Add subsidies attribute

    def step(self):
        # TODO: Add government actions here. Has to be based on a theory. BUT is this mandatory/necessary? Course description says we should focus on one actor?
        pass

# More agent classes can be added here, e.g. for insurance agents.
# This is not mandatory. I think we should leave it for now. We can add it later if we have time.
