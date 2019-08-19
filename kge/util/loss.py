import torch

from kge.util.sampler import KgeNegativeSampler


class KgeLoss:
    """ Wraps torch loss functions """

    def __init__(self):
        self._loss = None

    @staticmethod
    def create(config):
        """ Factory method for loss creation """
        # perhaps TODO: try class with specified name -> extensibility
        config.check("train.loss", ["bce", "margin_ranking"])
        if config.get("train.loss") == "bce":
            return BCEWithLogitsKgeLoss(reduction="mean", pos_weight=None)
        elif config.get("train.loss") == "margin_ranking":
            margin = config.get("train.loss_arg")
            return MarginRankingKgeLoss(margin, config, reduction="mean")
        else:
            raise ValueError("train.loss")

    def __call__(self, scores, labels, **kwargs):
        return self._compute_loss(scores, labels, **kwargs)

    def _compute_loss(self, scores, labels, **kwargs):
        raise NotImplementedError()


class BCEWithLogitsKgeLoss(KgeLoss):
    def __init__(self, reduction="mean", pos_weight=None):
        super().__init__()
        self._loss = torch.nn.BCEWithLogitsLoss(
            reduction=reduction, pos_weight=pos_weight
        )

    def _compute_loss(self, scores, labels, **kwargs):
        return self._loss(scores.view(-1), labels.view(-1))


class MarginRankingKgeLoss(KgeLoss):
    def __init__(self, margin, config, reduction="mean"):
        super().__init__()
        self._device = config.get("job.device")
        self._training_type = config.get("train.type")
        self._loss = torch.nn.MarginRankingLoss(margin=margin, reduction=reduction)

    def _compute_loss(self, scores, labels, **kwargs):
        # scores is (batch_size * num_negatives, 1)
        # labels is (batch_size * num_negatives)

        if "negative_sampling_spo" in self._training_type:
            # Pair each 1 with the following zeros until next 1
            pos_positives = labels.view(-1).nonzero().to(self._device).view(-1)
            pos_negatives = (labels.view(-1) == 0).nonzero().to(self._device).view(-1)
            # repeat each positive score num_negatives times
            pos_positives = pos_positives.view(-1, 1).repeat(1, kwargs['num_negatives']).view(-1)
            positives = scores[pos_positives].to(self._device).view(-1)
            negatives = scores[pos_negatives].to(self._device).view(-1)
            target = torch.ones(positives.size()).to(self._device)
            return self._loss(positives, negatives, target)

        elif "negative_sampling" in self._training_type:
            # Pair each 1 with the following zeros until next 1
            # num_positives = scores.size(0)//(1+kwargs['num_negatives'])
            pos_should_positives = torch.arange(0, scores.size(0), 1+kwargs['num_negatives'], device=self._device)
            should_negatives = torch.ones(labels.size(), device=self._device)
            should_negatives[pos_should_positives] = 0
            pos_should_negatives = (should_negatives == 1).nonzero().to(self._device).view(-1)
            # repeat each positive score num_negatives times
            pos_should_positives = pos_should_positives.view(-1, 1).repeat(1, kwargs['num_negatives']).view(-1)
            positives = scores[pos_should_positives].to(self._device).view(-1)
            negatives = scores[pos_should_negatives].to(self._device).view(-1)
            target = torch.ones(pos_should_positives.size()).to(self._device)
            return self._loss(positives, negatives, target)

        elif self._training_type == "1toN":
            # TODO determine how to form pairs for margin ranking in 1toN training
            # scores and labels are tensors of size (batch_size, num_entities)
            # Each row has 1s and 0s of a single sp or po tuple from training
            # How to combine them for pairs?
            # Each 1 with all 0s? Can memory handle this?
            raise NotImplementedError(
                "Margin ranking with 1toN training not yet supported."
            )
        else:
            raise ValueError("train.type for margin ranking.")
