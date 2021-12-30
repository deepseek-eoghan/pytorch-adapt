import copy

from ..containers import KeyEnforcer, MultipleContainers, Optimizers
from ..hooks import ADDAHook
from ..utils.common_functions import check_domain
from .base_adapter import BaseAdapter
from .utils import default_optimizer_tuple, with_opt


class ADDA(BaseAdapter):
    """
    Extends [BaseAdapter][pytorch_adapt.adapters.base_adapter.BaseAdapter]
    and wraps [ADDAHook][pytorch_adapt.hooks.adda].

    |Container|Required keys|
    |---|---|
    |models|```["G", "C", "D"]```|
    |optimizers|```["D", "T"]```|

    The target model ("T") is created during initialization by deep-copying the G model.
    """

    hook_cls = ADDAHook

    def inference_default(self, x, domain):
        """
        Arguments:
            x: The input to the model
            domain: If 0, then ```features = G(x)```
                Otherwise ```features = T(x)```.
        """
        domain = check_domain(self, domain)
        fe = "G" if domain == 0 else "T"
        features = self.models[fe](x)
        logits = self.models["C"](features)
        return features, logits

    def get_default_containers(self) -> MultipleContainers:
        """
        Returns:
            The default set of containers. This
            will create an Adam optimizer with lr 0.0001 for
            the T and D models.
        """
        optimizers = Optimizers(default_optimizer_tuple(), keys=["T", "D"])
        return MultipleContainers(optimizers=optimizers)

    def get_key_enforcer(self) -> KeyEnforcer:
        return KeyEnforcer(
            models=["G", "C", "D", "T"],
            optimizers=["D", "T"],
        )

    def init_hook(self, hook_kwargs):
        self.hook = self.hook_cls(
            d_opts=with_opt(["D"]), g_opts=with_opt(["T"]), **hook_kwargs
        )

    def init_containers_and_check_keys(self):
        self.containers["models"]["T"] = copy.deepcopy(self.containers["models"]["G"])
        super().init_containers_and_check_keys()
