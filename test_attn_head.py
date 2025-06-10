from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


class AttentionHeadAnalyzer:
    def __init__(self, model_name: str = "gpt2"):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name, output_attentions=True, torch_dtype=torch.float32
        ).to(self.device)

        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        self.model.eval()
        self.num_layers = self.model.config.n_layer
        self.num_heads = self.model.config.n_head

    def get_synthetic_data_samples(self) -> List[str]:
        synthetic_samples = [
            "The integration of quantum computing principles with classical algorithms represents a paradigm shift in computational efficiency.",
            "Advanced neural architectures demonstrate emergent capabilities through multi-layered attention mechanisms and residual connections.",
            "Human: What are the implications of transformer architecture? Assistant: Transformers revolutionized NLP through self-attention mechanisms.",
        ]
        return synthetic_samples

    def get_existing_data_samples(self) -> List[str]:
        existing_samples = [
            "Wikipedia is a free online encyclopedia, created and edited by volunteers around the world.",
            "The weather forecast shows sunny skies with temperatures reaching 75 degrees Fahrenheit.",
            "In the early morning hours, the city slowly awakens as commuters begin their daily journey to work.",
        ]
        return existing_samples

    def compute_attention_influence(self, text: str) -> Tuple[torch.Tensor, Dict]:
        inputs = self.tokenizer(
            text, return_tensors="pt", padding=True, truncation=True, max_length=512
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.model(**inputs, labels=inputs["input_ids"])
            base_loss = outputs.loss
            attentions = outputs.attentions

            attention_info = {
                "attentions": attentions,
                "input_ids": inputs["input_ids"],
                "attention_mask": inputs["attention_mask"],
            }

        return base_loss, attention_info

    def mask_attention_head(
        self, text: str, layer_idx: int, head_idx: int
    ) -> torch.Tensor:
        inputs = self.tokenizer(
            text, return_tensors="pt", padding=True, truncation=True, max_length=512
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        target_layer = self.model.transformer.h[layer_idx].attn

        original_weights = target_layer.c_proj.weight.data.clone()

        head_dim = self.model.config.n_embd // self.num_heads
        start_idx = head_idx * head_dim
        end_idx = (head_idx + 1) * head_dim

        target_layer.c_proj.weight.data[:, start_idx:end_idx] = 0

        try:
            with torch.no_grad():
                outputs = self.model(**inputs, labels=inputs["input_ids"])
                masked_loss = outputs.loss
        finally:
            target_layer.c_proj.weight.data = original_weights

        return masked_loss

    def analyze_head_importance(
        self, synthetic_samples: List[str], existing_samples: List[str]
    ) -> Dict:
        head_scores = np.zeros((self.num_layers, self.num_heads))

        print("Analyzing attention head sensitivity to synthetic vs existing data...")

        for layer_idx in range(self.num_layers):
            print(f"Processing layer {layer_idx + 1}/{self.num_layers}")

            for head_idx in range(self.num_heads):
                print(f"  Head {head_idx + 1}/{self.num_heads}", end=" ")
                synthetic_influence = []
                existing_influence = []

                for text in synthetic_samples:
                    base_loss, _ = self.compute_attention_influence(text)
                    masked_loss = self.mask_attention_head(text, layer_idx, head_idx)
                    influence = (masked_loss - base_loss).item()
                    synthetic_influence.append(influence)

                for text in existing_samples:
                    base_loss, _ = self.compute_attention_influence(text)
                    masked_loss = self.mask_attention_head(text, layer_idx, head_idx)
                    influence = (masked_loss - base_loss).item()
                    existing_influence.append(influence)

                synthetic_avg = np.mean(synthetic_influence)
                existing_avg = np.mean(existing_influence)
                head_scores[layer_idx, head_idx] = synthetic_avg - existing_avg
                print(f"Score: {head_scores[layer_idx, head_idx]:.4f}")

        return {
            "scores": head_scores,
            "top_heads": self.get_top_heads(head_scores),
            "interpretation": "Higher scores indicate heads more sensitive to synthetic data patterns",
        }

    def get_top_heads(
        self, head_scores: np.ndarray, top_k: int = 5
    ) -> List[Tuple[int, int, float]]:
        flat_indices = np.argsort(head_scores.flatten())[-top_k:]
        top_heads = []

        for flat_idx in reversed(flat_indices):
            layer_idx, head_idx = np.unravel_index(flat_idx, head_scores.shape)
            score = head_scores[layer_idx, head_idx]
            top_heads.append((layer_idx, head_idx, score))

        return top_heads

    def visualize_head_importance(self, head_scores: np.ndarray, save_path: str = None):
        plt.figure(figsize=(12, 8))
        sns.heatmap(
            head_scores,
            annot=True,
            fmt=".3f",
            cmap="RdYlBu_r",
            xticklabels=[f"Head {i}" for i in range(self.num_heads)],
            yticklabels=[f"Layer {i}" for i in range(self.num_layers)],
            center=0,
        )
        plt.title("Attention Head Sensitivity: Synthetic vs Existing Data")
        plt.xlabel("Attention Head")
        plt.ylabel("Layer")

        cbar = plt.gca().collections[0].colorbar
        cbar.set_label(
            "Influence Difference (Synthetic - Existing)", rotation=270, labelpad=20
        )

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches="tight")
        plt.show()


def main():
    analyzer = AttentionHeadAnalyzer("gpt2")

    synthetic_samples = analyzer.get_synthetic_data_samples()
    existing_samples = analyzer.get_existing_data_samples()

    results = analyzer.analyze_head_importance(synthetic_samples, existing_samples)

    print("\nTop 5 attention heads most sensitive to synthetic data:")
    for i, (layer, head, score) in enumerate(results["top_heads"]):
        print(f"{i + 1}. Layer {layer}, Head {head}: Score = {score:.4f}")

    print(f"\nInterpretation: {results['interpretation']}")

    analyzer.visualize_head_importance(results["scores"])

    return analyzer, results


if __name__ == "__main__":
    main()
