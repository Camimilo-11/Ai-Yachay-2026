import osmnx as ox
import heapq
from math import radians, sin, cos, sqrt, atan2

G = ox.graph_from_place("Urcuquí, Ecuador", network_type="drive")
print("Nodos:", len(G.nodes), "Aristas:", len(G.edges))

orig_node = ox.distance.nearest_nodes(G, X=-78.17021114574199, Y=0.40684388417122275)
dest_node = ox.distance.nearest_nodes(G, X=-78.19417413688504, Y=0.4174257342134235)


class Node:
    def __init__(self, state, parent, action, g):
        self.state = state
        self.parent = parent
        self.action = action
        self.g = g  # costo acumulado hasta aca

    
class PriorityFrontier:

    def __init__(self):
        self.heap = []
        self.counter = 0  # para que heapq no intente comparar Nodes cuando hay empate
        self.entries = {} # DICCIONARIO PARA FILTRAR CAMINOS QUE NO SIRVEN

    def add(self, node, f_score):
        self.counter += 1
        heapq.heappush(self.heap, (f_score, self.counter, node))
        self.entries[node.state] = node.g

    def empty(self):
        return len(self.heap) == 0

    def remove(self): #give thee node with the lowest f_score
        if self.empty():
            raise Exception("empty frontier")
        f_score, _, node = heapq.heappop(self.heap)
        return node

    def has_better(self, state, g):
        # si ya hay un camino mejor o igual a ese nodo en la frontera, no vale la pena meterlo de nuevo
        return state in self.entries and self.entries[state] <= g


def haversine(lat1, lon1, lat2, lon2):
    # distance of beeline
    R = 6371000
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2)**2 + cos(phi1) * cos(phi2) * sin(dlambda / 2)**2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def heuristic(node_id, goal_id, graph): # give the coordnates of the actual nodes and calculate the distance between them
    y1, x1 = graph.nodes[node_id]["y"], graph.nodes[node_id]["x"]
    y2, x2 = graph.nodes[goal_id]["y"], graph.nodes[goal_id]["x"]
    return haversine(y1, x1, y2, x2)
   


def edge_cost(graph, u, v, custom=False):
    data = min(graph.get_edge_data(u, v).values(), key=lambda d: d["length"])
    length = data["length"]

    if not custom:
        return length

    # mi criterio: evitar avenidas grandes, prefiero calles residenciales
    highway = data.get("highway", "")
    if isinstance(highway, list):
        highway = highway[0]

    if highway in ("primary", "secondary", "trunk"):
        return length * 2.0
    elif highway in ("residential", "living_street"):
        return length * 0.8
    return length


def astar(graph, start, goal, custom_cost=False):
    start_node = Node(state=start, parent=None, action=None, g=0)
    frontier = PriorityFrontier()
    frontier.add(start_node, f_score=heuristic(start, goal, graph))

    explored = set()
    num_explored = 0

    while True:
        if frontier.empty():
            raise Exception("no hay solución")

        node = frontier.remove()
        num_explored += 1

        if node.state == goal:
            # reconstruyo el camino subiendo por los padres
            path = []
            total_g = node.g
            while node.parent is not None:
                path.append(node.state)
                node = node.parent
            path.append(node.state)
            path.reverse()
            return path, total_g, num_explored

        if node.state in explored:
            continue
        explored.add(node.state)

        for neighbor in graph.neighbors(node.state):
            if neighbor in explored:
                continue
            step_cost = edge_cost(graph, node.state, neighbor, custom=custom_cost)
            g = node.g + step_cost

            if frontier.has_better(neighbor, g):
                continue

            h = heuristic(neighbor, goal, graph)
            child = Node(state=neighbor, parent=node, action=node.state, g=g)
            frontier.add(child, f_score=g + h)


my_path, my_cost, explored_count = astar(G, orig_node, dest_node, custom_cost=False)
nx_path = ox.shortest_path(G, orig_node, dest_node, weight="length")

print("\n--- Validación (costo = distancia) ---")
print("Mi A* coincide con NetworkX:", my_path == nx_path)
print("Costo mi A*:", round(my_cost, 1), "m")
print("Nodos explorados:", explored_count)

# ahora con mi costo personalizado
custom_path, custom_cost_val, custom_explored = astar(G, orig_node, dest_node, custom_cost=True)

print("\n--- Ruta con costo personalizado ---")
print("¿Misma ruta que la de distancia pura?:", custom_path == my_path)
print("Costo personalizado total:", round(custom_cost_val, 1))

real_dist_custom = sum(
    min(G.get_edge_data(u, v).values(), key=lambda d: d["length"])["length"]
    for u, v in zip(custom_path[:-1], custom_path[1:])
)
print("Distancia real de la ruta personalizada:", round(real_dist_custom, 1), "m")
print("Distancia real de la ruta más corta:", round(my_cost, 1), "m")


# baseline con BFS pa comparar (no le importa la distancia, solo cuenta saltos)
from collections import deque

def bfs(graph, start, goal):
    start_node = Node(state=start, parent=None, action=None, g=0)
    frontier = deque([start_node])
    explored = set()
    num_explored = 0

    while frontier:
        node = frontier.popleft()
        num_explored += 1

        if node.state == goal:
            path = []
            while node.parent is not None:
                path.append(node.state)
                node = node.parent
            path.append(node.state)
            path.reverse()
            return path, num_explored

        if node.state in explored:
            continue
        explored.add(node.state)

        for neighbor in graph.neighbors(node.state):
            if neighbor not in explored:
                frontier.append(Node(state=neighbor, parent=node, action=node.state, g=0))

    raise Exception("no hay solución")


bfs_path, bfs_explored = bfs(G, orig_node, dest_node)
bfs_dist = sum(
    min(G.get_edge_data(u, v).values(), key=lambda d: d["length"])["length"]
    for u, v in zip(bfs_path[:-1], bfs_path[1:])
)

print("\n--- Comparación con BFS (baseline) ---")
print("Nodos explorados BFS:", bfs_explored, "vs A*:", explored_count)
print("Distancia real ruta BFS:", round(bfs_dist, 1), "m")
print("Distancia real ruta A* (distancia):", round(my_cost, 1), "m")
print("¿BFS coincide con A* en costo=distancia?:", bfs_path == my_path)

ox.plot_graph_routes(
    G, [my_path, custom_path],
    route_colors=["yellow", "cyan"],
    route_linewidth=3, node_size=0
)