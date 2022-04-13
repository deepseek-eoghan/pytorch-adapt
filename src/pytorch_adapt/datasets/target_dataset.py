from typing import Any, Dict

from torch.utils.data import Dataset

from .domain_dataset import DomainDataset


class TargetDataset(DomainDataset):
    """
    Wrap your target dataset with this. Your target dataset's
    ```__getitem__``` function should return a tuple of ```(data, label)```.
    """

    def __init__(self, dataset: Dataset, domain: int = 1):
        """
        Arguments:
            dataset: The dataset to wrap
            domain: An integer representing the domain.
        """
        super().__init__(dataset, domain)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        """
        Returns:
            A dictionary with keys

            - "target_imgs" (the data)

            - "target_domain" (the integer representing the domain)

            - "target_sample_idx" (idx)
        """

        img, _ = self.dataset[idx]
        return {
            "target_imgs": img,
            "target_domain": self.domain,
            "target_sample_idx": idx,
        }
