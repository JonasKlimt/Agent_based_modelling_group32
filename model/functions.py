# -*- coding: utf-8 -*-
"""
@author: thoridwagenblast

Functions that are used in the model_file.py and agent.py for the running of the Flood Adaptation Model.
Functions get called by the Model and Agent class.
"""
import random
import numpy as np
import math
from shapely import contains_xy
from shapely import prepare
import geopandas as gpd
import rasterio as rs

def set_initial_values(input_data, parameter, seed):
    """
    Function to set the values based on the distribution shown in the input data for each parameter.
    The input data contains which percentage of households has a certain initial value.
    
    Parameters
    ----------
    input_data: the dataframe containing the distribution of paramters
    parameter: parameter name that is to be set
    seed: agent's seed
    
    Returns
    -------
    parameter_set: the value that is set for a certain agent for the specified parameter 
    """
    parameter_set = 0
    parameter_data = input_data.loc[(input_data.parameter == parameter)] # get the distribution of values for the specified parameter
    parameter_data = parameter_data.reset_index()
    random.seed(seed)
    random_parameter = random.randint(0,100) 
    for i in range(len(parameter_data)):
        if i == 0:
            if random_parameter < parameter_data['value_for_input'][i]:
                parameter_set = parameter_data['value'][i]
                break
        else:
            if (random_parameter >= parameter_data['value_for_input'][i-1]) and (random_parameter <= parameter_data['value_for_input'][i]):
                parameter_set = parameter_data['value'][i]
                break
            else:
                continue
    return parameter_set


def get_flood_map_data(flood_map):
    """
    Getting the flood map characteristics.
    
    Parameters
    ----------
    flood_map: flood map in tif format

    Returns
    -------
    band, bound_l, bound_r, bound_t, bound_b: characteristics of the tif-file
    """
    band = flood_map.read(1)
    bound_l = flood_map.bounds.left
    bound_r = flood_map.bounds.right
    bound_t = flood_map.bounds.top
    bound_b = flood_map.bounds.bottom
    return band, bound_l, bound_r, bound_t, bound_b

shapefile_path = r'../input_data/model_domain/houston_model/houston_model.shp'
floodplain_path = r'../input_data/floodplain/floodplain_area.shp'

# Model area setup
map_domain_gdf = gpd.GeoDataFrame.from_file(shapefile_path)
map_domain_gdf = map_domain_gdf.to_crs(epsg=26915)
map_domain_geoseries = map_domain_gdf['geometry']
map_minx, map_miny, map_maxx, map_maxy = map_domain_geoseries.total_bounds
map_domain_polygon = map_domain_geoseries[0]  # The geoseries contains only one polygon
prepare(map_domain_polygon)

# Floodplain setup
floodplain_gdf = gpd.GeoDataFrame.from_file(floodplain_path)
floodplain_gdf = floodplain_gdf.to_crs(epsg=26915)
floodplain_geoseries = floodplain_gdf['geometry']
floodplain_multipolygon = floodplain_geoseries[0]  # The geoseries contains only one multipolygon
prepare(floodplain_multipolygon)

def generate_random_location_within_map_domain():
    """
    Generate random location coordinates within the map domain polygon.

    Returns
    -------
    x, y: lists of location coordinates, longitude and latitude
    """
    while True:
        # generate random location coordinates within square area of map domain
        x = random.uniform(map_minx, map_maxx)
        y = random.uniform(map_miny, map_maxy)
        # check if the point is within the polygon, if so, return the coordinates
        if contains_xy(map_domain_polygon, x, y):
            return x, y

def get_flood_depth(corresponding_map, location, band):
    """ 
    To get the flood depth of a specific location within the model domain.
    Households are placed randomly on the map, so the distribution does not follow reality.
    
    Parameters
    ----------
    corresponding_map: flood map used
    location: household location (a Shapely Point) on the map
    band: band from the flood map

    Returns
    -------
    depth: flood depth at the given location
    """
    row, col = corresponding_map.index(location.x, location.y)
    depth = band[row -1, col -1]
    return depth
    

def get_position_flood(bound_l, bound_r, bound_t, bound_b, img, seed):
    """ 
    To generater the position on flood map for a household.
    Households are placed randomly on the map, so the distribution does not follow reality.
    
    Parameters
    ----------
    bound_l, bound_r, bound_t, bound_b, img: characteristics of the flood map data (.tif file)
    seed: seed to generate the location on the map

    Returns
    -------
    x, y: location on the map
    row, col: location within the tif-file
    """
    random.seed(seed)
    x = random.randint(round(bound_l, 0), round(bound_r, 0))
    y = random.randint(round(bound_b, 0), round(bound_t, 0))
    row, col = img.index(x, y)
    return x, y, row, col

# Function to calcualte flood damage when no adaptation measure is taken
def calculate_basic_flood_damage(flood_depth):
    """
    To get flood damage based on flood depth of household
    from de Moer, Huizinga (2017) with logarithmic regression over it.
    If flood depth > 6m, damage = 1.
    
    Parameters
    ----------
    flood_depth : flood depth as given by location within model domain

    Returns
    -------
    flood_damage : damage factor between 0 and 1
    """
    if flood_depth >= 6:
        flood_damage = 1
    elif flood_depth < 0.025:
        flood_damage = 0
    else:
        # see flood_damage.xlsx for function generation
        flood_damage = 0.1746 * math.log(flood_depth) + 0.6483
    return flood_damage * 100000 # multiply the flood damage with 100000 to get the damage in USD

# Function to calculate the flood damage when an adaptation measure is taken
def calculate_adapted_flood_damage(flood_depth):
    """
    To get flood damage based on flood depth of household
    from de Moer, Huizinga (2017) with logarithmic regression over it.
    Adapted equation: Flood adaptation measure taken by houshold, which elevates house by 1.3m
    If flood depth > 7m, damage = 1.
    
    Parameters
    ----------
    flood_depth : flood depth as given by location within model domain

    Returns
    -------
    flood_damage : damage factor between 0 and 1
    """
    if flood_depth >= 7:
        flood_damage = 1
    elif flood_depth < 1.025:
        flood_damage = 0
    else:
        # see flood_damage.xlsx for function generation (adapted to 1.m elevation)
        flood_damage = 0.1746 * math.log(flood_depth+1.3) + 0.6483
    return flood_damage * 100000 # multiply the flood damage with 100000 to get the damage in USD
#TODO: take hosuing size into consideration depending on income class?


# Expected utility based on the prospect theory, Source:
# Haer, T., Botzen, W. J. W., de Moel, H., & Aerts, J. C. J. H. (2017).
# Integrating Household Risk Mitigation Behavior in Flood Risk Analysis: An Agent-Based Model Approach.
# Risk Analysis, 37(10), 1977–1992. https://doi.org/10.1111/risa.12740

def expected_utility_prospect_theory(risk_of_flood, percieved_flood_damage, RPt, cost_of_measure, subsidie, action):
    """
    General utility function for the prospect theory model.

    Parameters:
    - risk_of_flood: Probability of a flood
    - percieved_flood_damage: Perceived flood damage
    - RPt: Risk perception
    - cost_of_measure: Cost of adaptation measure
    - subsidie: Subsidy for adaptation measure
    - action: Boolean variable indicating whether an adaptation measure is taken or not

    Returns:
    - expected_utility: Expected utility for action taken and no action taken
    """
    # Calculate the subjective weighting of the probability of a flood and the subjective Risk Perception at time t
    pi_i = subjective_weighting_probability_bayesian_PT(
            p_i=risk_of_flood,
            RPt=RPt,
    )   
    
    # Calculate the expected utility for action taken and no action taken
    if action:
        expected_utility = pi_i * utility_function_prospect_theory(-cost_of_measure+subsidie-calculate_adapted_flood_damage(percieved_flood_damage))
    else:
        expected_utility = pi_i * utility_function_prospect_theory(-calculate_basic_flood_damage(percieved_flood_damage))
        
    # retunr the expected utility and the updated risk perception
    return expected_utility
        

#def subjective_weighting_probability(pi, mean_delta=0.69, std_delta=0.025):
    """
    Calculate the subjective weighting of the probability of a flood.

    Parameters:
    - pi: Probability of a flood
    - mean_delta: Mean of the delta parameter
    - std_delta: Standard deviation of the delta parameter

    Returns:
    - Subjective weighting of the probability
    """
    
    delta = np.random.normal(mean_delta, std_delta) # delta: Heterogeneity parameter drawn from a random distribution for each household
    
    return pi ** delta / (pi ** delta + (1 - pi) ** delta) ** (1 / delta)

def subjective_weighting_probability_bayesian_PT(p_i, RPt, mean_delta=0.69, std_delta=0.025):
    """
    Calculate the subjective weighting of the probability of a flood.

    Parameters:
    - pi: Probability of a flood
    - RPt: Previous risk perception
    - mean_delta: Mean of the delta parameter
    - std_delta: Standard deviation of the delta parameter

    Returns:
    - Subjective weighting of the probability
    """
        
    delta = np.random.normal(mean_delta, std_delta) # delta: Heterogeneity parameter drawn from a random distribution for each household
    
    #RPt = risk_perception_bayesian_PT(RPt_1, I_social, I_media, flood_occurs) # Equation (6)
    
    pi_i = ((abs(10**(2 * RPt - 1) * p_i))**delta) / (((abs(10**(2 * RPt - 1) * p_i))**delta + (abs(1 - (10**(2 * RPt - 1) * p_i)))**delta)**(1/delta)) # Equation (7)
    
    return pi_i

def risk_perception_bayesian_PT(RPt_1, I_social, I_media, flood_occurs):
    """
    Calculate the subjective weighting of the probability of a flood.

    Parameters:
    - RPt_1: Previous risk perception
    - I_social: Social influence
    - I_media: Media influence
    - flood_occurs: Boolean variable indicating whether a flood occurs or not

    Returns:
    - Subjective weighting of the probability
    - RPt: Updated risk perception
    """
    
    # Parameters for the Bayesian Prospect Theory
    
    # The weight assigned to the experience, b ,is 1 if an individual experiences a flood. Otherwise,bis 0.04, causing risk perception to slowly return (4–6 years) to prior risk perceptions, which is in line with empirical evidence.
    # The weight a is 1, unless a flood occurs, in which case a is 1/10 the weight b assigned to experiencing a flood.
    if flood_occurs:
        b = 1
        a = 0.1
        I_experience = 1
    else:
        b = 0.04
        a = 1
        I_experience = 0
    
    # The parameters c and d thus assume a value of 0 if Isocial or Imedia is far from the own risk perception, 0.5 if it is intermediate, and 1 if Isocial or Imedia is close to the own risk perception. As in the work of Moussa ıd,τ is a threshold value of 0.2 to indicate the boundary of strong agreement.
    tau = 0.2
    # Equations (8) to (10)
    if abs(RPt_1 - I_social) < tau:
        c = 1
    elif abs(RPt_1 - I_social) > 1 - tau:
        c = 0
    else:
        c = 0.5
    
    if abs(RPt_1 - I_media) < tau:
        d = 1
    elif abs(RPt_1 - I_media) > 1 - tau:
        d = 0
    else:
        d = 0.5
    
    if RPt_1 == None:
        RPt_1 = 0.0
    
    # Equation (6)
    return (a * RPt_1 + b * I_experience + c * I_social + d * I_media) / (a + b + c + d)

def utility_function_prospect_theory(x, mean_lambda=2.25, std_lambda=1, mean_theta=0.88, std_theta=0.065):
    """
    General utility function for the prospect theory model.

    Parameters:
    - x: Outcome (gain or loss)
    - mean_lambda: Mean of the lambda parameter
    - std_lambda: Standard deviation of the lambda parameter
    - mean_theta: Mean of the theta parameter
    - std_theta: Standard deviation of the theta parameter

    Returns:
    - Utility for the outcome
    """
    
    lambda_val = np.random.normal(mean_lambda, std_lambda)
    theta = np.random.normal(mean_theta, std_theta)
    
    return -lambda_val * (-x) ** theta


def load_flood_map(flood_map_choice):
    """
    Initialize and set up the flood map related data based on the provided flood map choice.
    """
    # Define paths to flood maps
    flood_map_paths = {
        'harvey': r'../input_data/floodmaps/Harvey_depth_meters.tif',
        '100yr': r'../input_data/floodmaps/100yr_storm_depth_meters.tif',
        '500yr': r'../input_data/floodmaps/500yr_storm_depth_meters.tif' 
    }

    # Throw a ValueError if the flood map choice is not in the dictionary
    if flood_map_choice not in flood_map_paths.keys():
        raise ValueError(f"Unknown flood map choice: '{flood_map_choice}'. "
                            f"Currently implemented choices are: {list(flood_map_paths.keys())}")

    # Choose the appropriate flood map based on the input choice
    flood_map_path = flood_map_paths[flood_map_choice]

    # Loading and setting up the flood map
    return rs.open(flood_map_path)