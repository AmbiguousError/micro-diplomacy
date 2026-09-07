"""
Micro-Diplomacy Procedural Map Generator
Uses SciPy's Delaunay Triangulation to generate balanced, randomized planar graphs.
"""

import random
from typing import Any, Dict, Set
import numpy as np
from scipy.spatial import Delaunay

class MapGenerator:
    def __init__(self, num_nodes: int = 8, num_sc: int = 6):
        self.num_nodes = num_nodes
        self.num_sc = num_sc
        
    def generate_topology(self) -> Dict[str, Any]:
        """
        Generates a valid planar graph topology for seasonal tournaments.
        Guarantees no intersecting borders/edges.
        """
        # 1. Generate random 2D coordinates
        points = np.random.rand(self.num_nodes, 2)
        tri = Delaunay(points)
        
        # 2. Extract adjacency list from Delaunay simplices
        adjacency: Dict[int, Set[int]] = {i: set() for i in range(self.num_nodes)}
        for simplex in tri.simplices:
            for i in range(3):
                for j in range(i + 1, 3):
                    adjacency[simplex[i]].add(simplex[j])
                    adjacency[simplex[j]].add(simplex[i])
                    
        # 3. Assign node names
        names = [
            "Northreach", "Ironpeaks", "Westmarch", "Centerlands", 
            "Eastgate", "Sunport", "Southvale", "Duneport"
        ]
        random.shuffle(names)
        
        named_adjacency = {
            names[i]: list(names[neighbor] for neighbor in adjacency[i])
            for i in range(self.num_nodes)
        }
        
        # 4. Distribute Supply Centers (SCs)
        sc_nodes = random.sample(names, self.num_sc)
        
        # 5. Format layout payload for the frontend SVG renderer
        coordinates = {
            names[i]: {
                "x": round(float(points[i][0]) * 800, 1), 
                "y": round(float(points[i][1]) * 500, 1)
            } for i in range(self.num_nodes)
        }
        
        return {
            "adjacency": named_adjacency,
            "supply_centers": sc_nodes,
            "coordinates": coordinates
        }
