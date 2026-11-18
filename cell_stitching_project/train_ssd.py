from __future__ import annotations

import argparse
import itertools
import logging
import sys
from pathlib import Path

import torch
from torch.optim.lr_scheduler import CosineAnnealingLR, MultiStepLR
from torch.utils.data import ConcatDataset, DataLoader

from .ssd import vision as _vision  # noqa: F401
from .ssd.common import configure_torch_runtime, create_network_factory, store_label_file, str2bool
from .ssd.vision.datasets.voc_dataset import VOCDataset
from .ssd.vision.nn.multibox_loss import MultiboxLoss
from .ssd.vision.ssd.data_preprocessing import TestTransform, TrainAugmentation
from .ssd.vision.ssd.ssd import MatchPrior
from .ssd.vision.utils.misc import freeze_net_layers


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train an SSD model on VOC or Open Images style datasets.")
    parser.add_argument("--dataset-type", default="voc", choices=("voc", "open_images"))
    parser.add_argument("--datasets", "--data", nargs="+", required=True, help="Dataset directories.")
    parser.add_argument("--balance-data", action="store_true", help="Balance Open Images training data.")
    parser.add_argument("--net", default="mb1-ssd")
    parser.add_argument("--freeze-base-net", action="store_true")
    parser.add_argument("--freeze-net", action="store_true")
    parser.add_argument("--mb2-width-mult", default=1.0, type=float)
    parser.add_argument("--base-net", default=None)
    parser.add_argument("--pretrained-ssd", default=None)
    parser.add_argument("--resume", default=None)
    parser.add_argument("--lr", "--learning-rate", default=0.01, type=float)
    parser.add_argument("--momentum", default=0.9, type=float)
    parser.add_argument("--weight-decay", default=5e-4, type=float)
    parser.add_argument("--base-net-lr", default=0.001, type=float)
    parser.add_argument("--extra-layers-lr", default=None, type=float)
    parser.add_argument("--scheduler", default="cosine", choices=("cosine", "multi-step"))
    parser.add_argument("--milestones", default="80,100")
    parser.add_argument("--t-max", default=100.0, type=float)
    parser.add_argument("--batch-size", default=4, type=int)
    parser.add_argument("--num-epochs", "--epochs", default=30, type=int)
    parser.add_argument("--num-workers", "--workers", default=0, type=int)
    parser.add_argument("--validation-epochs", default=1, type=int)
    parser.add_argument("--debug-steps", default=10, type=int)
    parser.add_argument("--use-cuda", default=True, type=str2bool)
    parser.add_argument("--checkpoint-folder", "--model-dir", default="models/ssd")
    return parser


def _build_dataset(dataset_type: str, dataset_path: Path, train: bool, train_transform, target_transform, test_transform, balance_data: bool):
    if dataset_type == "voc":
        transform = train_transform if train else test_transform
        return VOCDataset(dataset_path, transform=transform, target_transform=target_transform, is_test=not train)
    from .ssd.vision.datasets.open_images import OpenImagesDataset

    return OpenImagesDataset(
        dataset_path,
        transform=train_transform if train else test_transform,
        target_transform=target_transform,
        dataset_type="train" if train else "test",
        balance_data=balance_data if train else False,
    )


def _train_one_epoch(loader, net, criterion, optimizer, device, debug_steps: int, epoch: int) -> None:
    net.train(True)
    running_loss = 0.0
    running_reg = 0.0
    running_cls = 0.0
    for step, (images, boxes, labels) in enumerate(loader):
        images = images.to(device)
        boxes = boxes.to(device)
        labels = labels.to(device)

        optimizer.zero_grad()
        confidence, locations = net(images)
        regression_loss, classification_loss = criterion(confidence, locations, labels, boxes)
        loss = regression_loss + classification_loss
        loss.backward()
        optimizer.step()

        running_loss += float(loss.item())
        running_reg += float(regression_loss.item())
        running_cls += float(classification_loss.item())
        if step and step % debug_steps == 0:
            logging.info(
                "Epoch %d Step %d/%d AvgLoss=%.4f AvgReg=%.4f AvgCls=%.4f",
                epoch,
                step,
                len(loader),
                running_loss / debug_steps,
                running_reg / debug_steps,
                running_cls / debug_steps,
            )
            running_loss = 0.0
            running_reg = 0.0
            running_cls = 0.0


def _evaluate(loader, net, criterion, device):
    net.eval()
    total_loss = 0.0
    total_reg = 0.0
    total_cls = 0.0
    batches = 0
    for images, boxes, labels in loader:
        images = images.to(device)
        boxes = boxes.to(device)
        labels = labels.to(device)
        with torch.no_grad():
            confidence, locations = net(images)
            regression_loss, classification_loss = criterion(confidence, locations, labels, boxes)
            loss = regression_loss + classification_loss
        batches += 1
        total_loss += float(loss.item())
        total_reg += float(regression_loss.item())
        total_cls += float(classification_loss.item())
    if batches == 0:
        raise RuntimeError("Validation dataset is empty.")
    return total_loss / batches, total_reg / batches, total_cls / batches


def main() -> int:
    args = _parser().parse_args()
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(asctime)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    checkpoint_dir = Path(args.checkpoint_folder)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    create_net, config = create_network_factory(args.net, mb2_width_mult=args.mb2_width_mult)
    device = configure_torch_runtime(use_cuda=args.use_cuda)

    train_transform = TrainAugmentation(config.image_size, config.image_mean, config.image_std)
    target_transform = MatchPrior(config.priors, config.center_variance, config.size_variance, 0.5)
    test_transform = TestTransform(config.image_size, config.image_mean, config.image_std)

    dataset_paths = [Path(path) for path in args.datasets]
    train_sets = []
    val_sets = []
    expected_classes: tuple[str, ...] | None = None
    for dataset_path in dataset_paths:
        train_dataset = _build_dataset(
            dataset_type=args.dataset_type,
            dataset_path=dataset_path,
            train=True,
            train_transform=train_transform,
            target_transform=target_transform,
            test_transform=test_transform,
            balance_data=args.balance_data,
        )
        val_dataset = _build_dataset(
            dataset_type=args.dataset_type,
            dataset_path=dataset_path,
            train=False,
            train_transform=train_transform,
            target_transform=target_transform,
            test_transform=test_transform,
            balance_data=args.balance_data,
        )
        class_names = tuple(train_dataset.class_names)
        if expected_classes is None:
            expected_classes = class_names
        elif class_names != expected_classes:
            raise ValueError("All datasets must expose the same class names in the same order.")
        train_sets.append(train_dataset)
        val_sets.append(val_dataset)

    if expected_classes is None:
        raise RuntimeError("No training datasets were loaded.")
    label_file = store_label_file(checkpoint_dir / "labels.txt", list(expected_classes))
    logging.info("Stored labels in %s", label_file)

    train_loader = DataLoader(ConcatDataset(train_sets), args.batch_size, num_workers=args.num_workers, shuffle=True)
    val_loader = DataLoader(ConcatDataset(val_sets), args.batch_size, num_workers=args.num_workers, shuffle=False)

    net = create_net(len(expected_classes))
    if args.resume:
        logging.info("Resuming from %s", args.resume)
        net.load(args.resume)
    elif args.base_net:
        logging.info("Initializing base net from %s", args.base_net)
        net.init_from_base_net(args.base_net)
    elif args.pretrained_ssd and Path(args.pretrained_ssd).exists():
        logging.info("Initializing from pretrained SSD %s", args.pretrained_ssd)
        net.init_from_pretrained_ssd(args.pretrained_ssd)
    else:
        logging.info("Initializing SSD weights from scratch.")
        net.init()

    base_net_lr = args.base_net_lr if args.base_net_lr is not None else args.lr
    extra_layers_lr = args.extra_layers_lr if args.extra_layers_lr is not None else args.lr
    if args.freeze_base_net:
        freeze_net_layers(net.base_net)
        params = [
            {"params": itertools.chain(net.source_layer_add_ons.parameters(), net.extras.parameters()), "lr": extra_layers_lr},
            {"params": itertools.chain(net.regression_headers.parameters(), net.classification_headers.parameters())},
        ]
    elif args.freeze_net:
        freeze_net_layers(net.base_net)
        freeze_net_layers(net.source_layer_add_ons)
        freeze_net_layers(net.extras)
        params = itertools.chain(net.regression_headers.parameters(), net.classification_headers.parameters())
    else:
        params = [
            {"params": net.base_net.parameters(), "lr": base_net_lr},
            {"params": itertools.chain(net.source_layer_add_ons.parameters(), net.extras.parameters()), "lr": extra_layers_lr},
            {"params": itertools.chain(net.regression_headers.parameters(), net.classification_headers.parameters())},
        ]

    net.to(device)
    criterion = MultiboxLoss(config.priors, iou_threshold=0.5, neg_pos_ratio=3, center_variance=0.1, size_variance=0.2, device=device)
    optimizer = torch.optim.SGD(params, lr=args.lr, momentum=args.momentum, weight_decay=args.weight_decay)
    scheduler = (
        MultiStepLR(optimizer, milestones=[int(value.strip()) for value in args.milestones.split(",") if value.strip()], gamma=0.1)
        if args.scheduler == "multi-step"
        else CosineAnnealingLR(optimizer, args.t_max)
    )

    for epoch in range(args.num_epochs):
        _train_one_epoch(train_loader, net, criterion, optimizer, device, debug_steps=args.debug_steps, epoch=epoch)
        if epoch % args.validation_epochs == 0 or epoch == args.num_epochs - 1:
            val_loss, val_reg, val_cls = _evaluate(val_loader, net, criterion, device)
            logging.info(
                "Epoch %d ValidationLoss=%.4f ValidationReg=%.4f ValidationCls=%.4f",
                epoch,
                val_loss,
                val_reg,
                val_cls,
            )
            model_path = checkpoint_dir / f"{args.net}-Epoch-{epoch}-Loss-{val_loss:.6f}.pth"
            net.save(str(model_path))
            logging.info("Saved model %s", model_path)
        scheduler.step()

    print(f"checkpoint_dir={checkpoint_dir.resolve()}")
    print(f"labels={label_file.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
