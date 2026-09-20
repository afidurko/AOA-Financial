"""Neural endpoint mesh — unified graph of every AOA endpoint with memory.

Meshes runtime endpoints (broker, LLM, dashboard, notifiers, vault,
companion services) with the brain graph (members, algorithms, loops,
spines) into one weighted graph, and persists a Hebbian-style run memory
under ``data/{env}/mesh/`` so completion and correctness compound across
runs.
"""

from aoa.mesh.graph import MeshEdge, MeshMemory, MeshNode, NeuralEndpointMesh

__all__ = ["MeshEdge", "MeshMemory", "MeshNode", "NeuralEndpointMesh"]
