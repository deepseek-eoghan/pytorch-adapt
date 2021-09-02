import re

import torch

from ..utils import common_functions as c_f
from .base import BaseHook, BaseWrapperHook
from .utils import ChainHook


class BaseFeaturesHook(BaseHook):
    def __init__(
        self,
        model_name,
        in_suffixes=None,
        out_suffixes=None,
        domains=None,
        detach=False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.model_name = model_name
        self.domains = c_f.default(domains, ["src", "target"])
        self.init_detach_mode(detach)
        self.init_suffixes(in_suffixes, out_suffixes)

    def call(self, losses, inputs):
        outputs = {}
        for domain in self.domains:
            detach = self.check_grad_mode(domain)
            func = self.mode_detached if detach else self.mode_with_grad
            in_keys = c_f.filter(self.in_keys, f"^{domain}")
            func(inputs, outputs, domain, in_keys)

        self.check_outputs_requires_grad(outputs)
        return {}, outputs

    def check_grad_mode(self, domain):
        detach = self.detach[domain]
        if not torch.is_grad_enabled():
            if not detach:
                raise ValueError(
                    f"detach[{domain}] == {detach} but grad is not enabled"
                )
        return detach

    def check_outputs_requires_grad(self, outputs):
        for k, v in outputs.items():
            if k.endswith("detached") and c_f.requires_grad(v, does=True):
                raise TypeError(f"{k} ends with 'detached' but tensor requires grad")
            if not k.endswith("detached") and c_f.requires_grad(v, does=False):
                raise TypeError(
                    f"{k} doesn't end in 'detached' but tensor doesn't require grad"
                )

    def mode_with_grad(self, inputs, outputs, domain, in_keys):
        output_keys = c_f.filter(self._out_keys(), f"^{domain}")
        output_vals = self.get_kwargs(inputs, output_keys)
        self.add_if_new(
            outputs, output_keys, output_vals, inputs, self.model_name, in_keys, domain
        )
        return output_keys, output_vals

    def mode_detached(self, inputs, outputs, domain, in_keys):
        curr_out_keys = c_f.filter(self._out_keys(), f"^{domain}")
        self.try_existing_detachable(inputs, outputs, curr_out_keys)
        remaining_out_keys = [
            k for k in curr_out_keys if k not in set().union(inputs, outputs)
        ]
        if len(remaining_out_keys) > 0:
            output_vals = self.get_kwargs(inputs, remaining_out_keys)
            with torch.no_grad():
                self.add_if_new(
                    outputs,
                    remaining_out_keys,
                    output_vals,
                    inputs,
                    self.model_name,
                    in_keys,
                    domain,
                )

    def add_if_new(
        self, outputs, full_key, output_vals, inputs, model_name, in_keys, domain
    ):
        c_f.add_if_new(outputs, full_key, output_vals, inputs, model_name, in_keys)

    def create_keys(self, domain, suffix, starting_keys=None, detach=False):
        if starting_keys is None:
            full_keys = [f"{domain}{x}" for x in suffix]
        else:
            if len(starting_keys) > 1:
                starting_keys = self.join_keys(starting_keys)
            if len(suffix) > 1:
                starting_keys = starting_keys * len(suffix)
            full_keys = [f"{k}{x}" for k, x in zip(starting_keys, suffix)]
        if detach:
            full_keys = self.add_detached_string(full_keys)
        return full_keys

    def get_kwargs(self, inputs, keys):
        return [inputs.get(k) for k in keys]

    def try_existing_detachable(self, inputs, outputs, curr_out_keys):
        for k in curr_out_keys:
            if k in inputs or k in outputs:
                continue
            curr_regex = self.detachable_regex[k]
            success = self.try_existing_detachable_in_dict(
                curr_regex, inputs, outputs, k
            )
            if not success:
                self.try_existing_detachable_in_dict(curr_regex, outputs, outputs, k)

    def try_existing_detachable_in_dict(self, regex, in_dict, outputs, new_k):
        for k, v in in_dict.items():
            if regex.search(k) and v is not None:
                outputs[new_k] = v.detach()
                return True
        return False

    def find_detachable(self, keys):
        keys = [k.replace("_", "")]

    def add_detached_string(self, keys):
        # delete existing detached string, then append to the very end
        # for example, if computing detached logits for: src_imgs_features_detached
        # 1. src_imgs_features_detached_logits --> src_imgs_features_logits
        # 2. src_imgs_features_logits --> src_imgs_features_logits_detached
        keys = [k.replace("_detached", "") for k in keys]
        return [f"{k}_detached" for k in keys]

    def join_keys(self, keys):
        return ["_AND_".join(keys)]

    def init_detach_mode(self, detach):
        if isinstance(detach, dict):
            if any(not isinstance(v, bool) for v in detach.values()):
                raise TypeError("if detach is a dict, values must be bools")
            self.detach = detach
        elif isinstance(detach, bool):
            self.detach = {k: detach for k in self.domains}
        else:
            raise TypeError("detach must be a bool or a dict of bools")

    def init_suffixes(self, in_suffixes, out_suffixes):
        self.in_suffixes = in_suffixes
        self.out_suffixes = out_suffixes
        in_keys = []
        for domain in self.domains:
            in_keys.extend(self.create_keys(domain, in_suffixes))
        self.set_in_keys(in_keys)

    def set_in_keys(self, in_keys):
        super().set_in_keys(in_keys)
        self.all_out_keys = []
        for domain in self.domains:
            curr_in_keys = c_f.filter(self.in_keys, f"^{domain}")
            curr_out_keys = self.create_keys(
                domain, self.out_suffixes, curr_in_keys, detach=self.detach[domain]
            )
            self.all_out_keys.extend(curr_out_keys)

        # strings with '_detached' optional and anywhere
        self.detachable_regex = {
            k: re.compile(
                f"^{k.replace('_detached', '').replace('_', '(_detached)?_')}$"
            )
            for k in self.all_out_keys
        }

    def _loss_keys(self):
        return []

    def _out_keys(self):
        return self.all_out_keys

    def extra_repr(self):
        return c_f.extra_repr(self, ["model_name", "domains", "detach"])


class FeaturesHook(BaseFeaturesHook):
    def __init__(
        self,
        model_name="G",
        in_suffixes=None,
        out_suffixes=None,
        **kwargs,
    ):
        in_suffixes = c_f.default(in_suffixes, ["_imgs"])
        out_suffixes = c_f.default(out_suffixes, ["_features"])
        super().__init__(
            model_name=model_name,
            in_suffixes=in_suffixes,
            out_suffixes=out_suffixes,
            **kwargs,
        )


class LogitsHook(BaseFeaturesHook):
    def __init__(
        self,
        model_name="C",
        in_suffixes=None,
        out_suffixes=None,
        **kwargs,
    ):
        in_suffixes = c_f.default(in_suffixes, ["_imgs_features"])
        out_suffixes = c_f.default(out_suffixes, ["_logits"])
        super().__init__(
            model_name=model_name,
            in_suffixes=in_suffixes,
            out_suffixes=out_suffixes,
            **kwargs,
        )


class FeaturesChainHook(ChainHook):
    def __init__(
        self,
        *hooks,
        **kwargs,
    ):
        for i in range(len(hooks) - 1):
            hooks[i + 1].set_in_keys(hooks[i].out_keys)
        super().__init__(*hooks, **kwargs)


class FeaturesAndLogitsHook(FeaturesChainHook):
    def __init__(
        self,
        domains=None,
        detach_features=False,
        detach_logits=False,
        other_hooks=None,
        **kwargs,
    ):
        features_hook = FeaturesHook(detach=detach_features, domains=domains)
        logits_hook = LogitsHook(detach=detach_logits, domains=domains)
        other_hooks = c_f.default(other_hooks, [])
        super().__init__(features_hook, logits_hook, *other_hooks, **kwargs)


class FeaturesWithGradAndDetachedHook(BaseWrapperHook):
    def __init__(
        self,
        model_name="G",
        in_suffixes=None,
        out_suffixes=None,
        domains=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        hooks = []
        for detach in [False, True]:
            hooks.append(
                FeaturesHook(
                    model_name=model_name,
                    in_suffixes=in_suffixes,
                    out_suffixes=out_suffixes,
                    domains=domains,
                    detach=detach,
                    **kwargs,
                )
            )
        self.hook = ChainHook(*hooks)


class CombinedFeaturesHook(BaseFeaturesHook):
    def __init__(
        self,
        in_suffixes=None,
        out_suffixes=None,
        **kwargs,
    ):
        in_suffixes = c_f.default(
            in_suffixes, ["_imgs_features", "_imgs_features_logits"]
        )
        out_suffixes = c_f.default(out_suffixes, ["_combined"])
        super().__init__(
            model_name="feature_combiner",
            in_suffixes=in_suffixes,
            out_suffixes=out_suffixes,
            **kwargs,
        )


class DLogitsHook(BaseFeaturesHook):
    def __init__(
        self,
        model_name="D",
        in_suffixes=None,
        out_suffixes=None,
        **kwargs,
    ):
        in_suffixes = c_f.default(in_suffixes, ["_imgs_features"])
        out_suffixes = c_f.default(out_suffixes, ["_dlogits"])
        super().__init__(
            model_name=model_name,
            in_suffixes=in_suffixes,
            out_suffixes=out_suffixes,
            **kwargs,
        )


class FrozenModelHook(BaseWrapperHook):
    def __init__(self, hook, model_name, **kwargs):
        super().__init__(**kwargs)
        self.hook = hook
        self.model_name = model_name

    def call(self, losses, inputs):
        model = inputs[self.model_name]
        model.eval()
        with torch.no_grad():
            losses, outputs = self.hook(losses, inputs)
        return losses, outputs