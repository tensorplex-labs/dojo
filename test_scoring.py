import matplotlib.pyplot as plt
import numpy as np
import torch
from sklearn.cluster import DBSCAN


def get_optimal_eps(data_tensor, safety_factor=0.5):
    """Calculate optimal eps for DBSCAN to guarantee clustering of unique values."""
    unique_values = torch.unique(data_tensor)
    if len(unique_values) <= 1:
        return 0.001

    sorted_values = torch.sort(unique_values)[0]
    min_spacing = torch.min(torch.diff(sorted_values))
    return min_spacing.item() * safety_factor


# tensor = torch.load("dojo-vali-mainnet-scores.pt")


# Generate single tensor with n_unique_values discrete values between 0-1
n_unique_values = 10
unique_vals = np.linspace(0, 1, n_unique_values)
tensor_vals = np.random.choice(unique_vals, size=256)
single_tensor = torch.from_numpy(tensor_vals).float()
# Normalize to sum to 1
single_tensor = single_tensor / torch.sum(single_tensor)

# For clustering analysis, we need to look at the 256 individual values as data points
# Each value in the tensor becomes a data point for clustering
data_points = single_tensor.numpy().reshape(
    -1, 1
)  # Reshape to column vector for clustering
# value = 1 / 256
# tensor = torch.full((1, 256), value)
variance = torch.var(single_tensor)  # Population variance
variance_unbiased = torch.var(single_tensor, unbiased=True)  # Sample variance

# Manual calculation
mean = torch.mean(single_tensor)
variance_manual = torch.mean((single_tensor - mean) ** 2)

# Print actual unique values after normalization to see spacing
actual_unique_values = torch.unique(single_tensor)
print(f"Number of actual unique values: {len(actual_unique_values)}")
print(f"Actual unique values: {actual_unique_values}")
if len(actual_unique_values) > 1:
    min_spacing = torch.min(torch.diff(torch.sort(actual_unique_values)[0]))
    print(f"Minimum spacing between values: {min_spacing}")

# DBSCAN clustering on the 256 values
eps_value = get_optimal_eps(single_tensor)
print(f"Using eps: {eps_value:.6f}")
dbscan = DBSCAN(eps=eps_value, min_samples=2)
dbscan_labels = dbscan.fit_predict(data_points)

print(f"DBSCAN cluster assignments for 256 values: {dbscan_labels}")
print(
    f"DBSCAN found {len(set(dbscan_labels)) - (1 if -1 in dbscan_labels else 0)} clusters"
)
print(f"DBSCAN noise points: {np.sum(dbscan_labels == -1)}")

# Find duplicate values (values in same cluster)
print("\nDBSCAN duplicate values:")
unique_clusters = set(dbscan_labels) - {-1}
for cluster_id in unique_clusters:
    cluster_indices = np.where(dbscan_labels == cluster_id)[0]
    cluster_values = single_tensor[cluster_indices]
    if len(cluster_indices) > 1:
        print(
            f"Cluster {cluster_id} has {len(cluster_indices)} values: {cluster_values.unique().tolist()}"
        )

print(f"{data_points.shape=}")
print(f"{single_tensor=}")
print(f"{variance=}")
print(f"{variance_unbiased=}")

# Plot results
tensor_sorted = torch.sort(single_tensor, descending=True)[0]
plt.figure(figsize=(12, 8))

# Plot 1: Tensor values with cluster colors
plt.subplot(2, 2, 1)
scatter = plt.scatter(
    range(256), single_tensor.numpy(), c=dbscan_labels, cmap="viridis", alpha=0.7
)
plt.title("Tensor Values Colored by DBSCAN Clusters")
plt.xlabel("Index")
plt.ylabel("Value")
plt.colorbar(scatter)
plt.grid(True)

# Plot 2: Sorted tensor values
plt.subplot(2, 2, 2)
plt.plot(tensor_sorted.numpy())
plt.title("Sorted Tensor Values")
plt.xlabel("Index")
plt.ylabel("Value")
plt.grid(True)

# Plot 3: Value distribution histogram
plt.subplot(2, 2, 3)
plt.hist(single_tensor.numpy(), bins=20, alpha=0.7, edgecolor="black")
plt.title("Value Distribution")
plt.xlabel("Value")
plt.ylabel("Frequency")
plt.grid(True)

# Plot 4: Cluster size distribution
plt.subplot(2, 2, 4)
unique_labels = set(dbscan_labels)
cluster_sizes = []
cluster_ids = []
for label in unique_labels:
    if label != -1:
        cluster_sizes.append(np.sum(dbscan_labels == label))
        cluster_ids.append(label)
noise_count = np.sum(dbscan_labels == -1)

plt.bar(cluster_ids, cluster_sizes, alpha=0.7, label="Clusters")
if noise_count > 0:
    plt.bar("Noise", noise_count, alpha=0.7, color="red", label="Noise")
plt.title("Cluster Size Distribution")
plt.xlabel("Cluster ID")
plt.ylabel("Number of Values")
plt.legend()
plt.grid(True)

plt.tight_layout()
plt.show()
