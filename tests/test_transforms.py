# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved.

import unittest
from collections import Counter

import numpy as np
import torch
from pytorchvideo.data.utils import thwc_to_cthw
from pytorchvideo.transforms import (
    ApplyTransformToKey,
    CutMix,
    MixUp,
    Normalize,
    OpSampler,
    RandAugment,
    RandomShortSideScale,
    UniformCropVideo,
    UniformTemporalSubsample,
)
from pytorchvideo.transforms.functional import (
    convert_to_one_hot,
    short_side_scale,
    short_side_scale_with_boxes,
    random_short_side_scale_with_boxes,
    uniform_crop,
    uniform_crop_with_boxes,
    random_crop_with_boxes,
    horizontal_flip_with_boxes,
    clip_boxes_to_image,
    uniform_temporal_subsample,
    uniform_temporal_subsample_repeated,
)
from torchvision.transforms import Compose
from torchvision.transforms._transforms_video import (
    NormalizeVideo,
    RandomCropVideo,
    RandomHorizontalFlipVideo,
)
from utils import create_dummy_video_frames, create_random_bbox


class TestTransforms(unittest.TestCase):
    def test_compose_with_video_transforms(self):
        video = thwc_to_cthw(create_dummy_video_frames(20, 30, 40)).to(
            dtype=torch.float32
        )
        test_clip = {"video": video, "label": 0}

        # Compose using torchvision and pytorchvideo transformst to ensure they interact
        # correctly.
        num_subsample = 10
        transform = Compose(
            [
                ApplyTransformToKey(
                    key="video",
                    transform=Compose(
                        [
                            UniformTemporalSubsample(num_subsample),
                            NormalizeVideo([video.mean()] * 3, [video.std()] * 3),
                            RandomShortSideScale(min_size=15, max_size=25),
                            RandomCropVideo(10),
                            RandomHorizontalFlipVideo(p=0.5),
                        ]
                    ),
                )
            ]
        )

        actual = transform(test_clip)
        c, t, h, w = actual["video"].shape
        self.assertEqual(c, 3)
        self.assertEqual(t, num_subsample)
        self.assertEqual(h, 10)
        self.assertEqual(w, 10)

    def test_uniform_temporal_subsample(self):
        video = thwc_to_cthw(create_dummy_video_frames(20, 30, 40)).to(
            dtype=torch.float32
        )
        actual = uniform_temporal_subsample(video, video.shape[1])
        self.assertTrue(actual.equal(video))

        video = thwc_to_cthw(create_dummy_video_frames(20, 30, 40)).to(
            dtype=torch.float32
        )
        actual = uniform_temporal_subsample(video, video.shape[1] // 2)
        self.assertTrue(actual.equal(video[:, [0, 2, 4, 6, 8, 10, 12, 14, 16, 19]]))

        video = thwc_to_cthw(create_dummy_video_frames(20, 30, 40)).to(
            dtype=torch.float32
        )
        actual = uniform_temporal_subsample(video, 1)
        self.assertTrue(actual.equal(video[:, 0:1]))

    def test_short_side_scale_width_shorter_pytorch(self):
        video = thwc_to_cthw(create_dummy_video_frames(20, 20, 10)).to(
            dtype=torch.float32
        )
        actual = short_side_scale(video, 5, backend="pytorch")
        self.assertEqual(actual.shape, (3, 20, 10, 5))

    def test_short_side_scale_height_shorter_pytorch(self):
        video = thwc_to_cthw(create_dummy_video_frames(20, 10, 20)).to(
            dtype=torch.float32
        )
        actual = short_side_scale(video, 5, backend="pytorch")
        self.assertEqual(actual.shape, (3, 20, 5, 10))

    def test_short_side_scale_equal_size_pytorch(self):
        video = thwc_to_cthw(create_dummy_video_frames(20, 10, 10)).to(
            dtype=torch.float32
        )
        actual = short_side_scale(video, 10, backend="pytorch")
        self.assertEqual(actual.shape, (3, 20, 10, 10))

    def test_short_side_scale_width_shorter_opencv(self):
        video = thwc_to_cthw(create_dummy_video_frames(20, 20, 10)).to(
            dtype=torch.float32
        )
        actual = short_side_scale(video, 5, backend="opencv")
        self.assertEqual(actual.shape, (3, 20, 10, 5))

    def test_short_side_scale_height_shorter_opencv(self):
        video = thwc_to_cthw(create_dummy_video_frames(20, 10, 20)).to(
            dtype=torch.float32
        )
        actual = short_side_scale(video, 5, backend="opencv")
        self.assertEqual(actual.shape, (3, 20, 5, 10))

    def test_short_side_scale_equal_size_opencv(self):
        video = thwc_to_cthw(create_dummy_video_frames(20, 10, 10)).to(
            dtype=torch.float32
        )
        actual = short_side_scale(video, 10, backend="opencv")
        self.assertEqual(actual.shape, (3, 20, 10, 10))

    def test_random_short_side_scale_height_shorter_pytorch_with_boxes(self):
        video = thwc_to_cthw(create_dummy_video_frames(20, 10, 20)).to(
            dtype=torch.float32
        )
        boxes = create_random_bbox(7, 10, 20)
        actual, scaled_boxes = random_short_side_scale_with_boxes(
            video, min_size=4, max_size=8, backend="pytorch", boxes=boxes
        )
        self.assertEqual(actual.shape[0], 3)
        self.assertEqual(actual.shape[1], 20)
        self.assertTrue(actual.shape[2] <= 8 and actual.shape[2] >= 4)
        self._check_boxes(7, actual.shape[2], actual.shape[3], boxes)

    def test_short_side_scale_height_shorter_pytorch_with_boxes(self):
        video = thwc_to_cthw(create_dummy_video_frames(20, 10, 20)).to(
            dtype=torch.float32
        )
        boxes = create_random_bbox(7, 10, 20)
        actual, scaled_boxes = short_side_scale_with_boxes(
            video,
            boxes=boxes,
            size=5,
            backend="pytorch",
        )
        self.assertEqual(actual.shape, (3, 20, 5, 10))
        self._check_boxes(7, 5, 10, boxes)

    def test_torchscriptable_input_output(self):
        video = thwc_to_cthw(create_dummy_video_frames(20, 30, 40)).to(
            dtype=torch.float32
        )

        # Test all the torchscriptable tensors.
        for transform in [UniformTemporalSubsample(10), RandomShortSideScale(10, 20)]:

            transform_script = torch.jit.script(transform)
            self.assertTrue(isinstance(transform_script, torch.jit.ScriptModule))

            # Seed before each transform to force determinism.
            torch.manual_seed(0)
            output = transform(video)
            torch.manual_seed(0)
            script_output = transform_script(video)
            self.assertTrue(output.equal(script_output))

    def test_uniform_temporal_subsample_repeated(self):
        video = thwc_to_cthw(create_dummy_video_frames(32, 10, 10)).to(
            dtype=torch.float32
        )
        actual = uniform_temporal_subsample_repeated(video, (1, 4))
        expected_shape = ((3, 32, 10, 10), (3, 8, 10, 10))
        for idx in range(len(actual)):
            self.assertEqual(actual[idx].shape, expected_shape[idx])

    def test_uniform_crop(self):
        # For videos with height < width.
        video = thwc_to_cthw(create_dummy_video_frames(20, 30, 40)).to(
            dtype=torch.float32
        )
        # Left crop.
        actual = uniform_crop(video, size=20, spatial_idx=0)
        self.assertTrue(actual.equal(video[:, :, 5:25, :20]))
        # Center crop.
        actual = uniform_crop(video, size=20, spatial_idx=1)
        self.assertTrue(actual.equal(video[:, :, 5:25, 10:30]))
        # Right crop.
        actual = uniform_crop(video, size=20, spatial_idx=2)
        self.assertTrue(actual.equal(video[:, :, 5:25, 20:]))

        # For videos with height > width.
        video = thwc_to_cthw(create_dummy_video_frames(20, 40, 30)).to(
            dtype=torch.float32
        )
        # Top crop.
        actual = uniform_crop(video, size=20, spatial_idx=0)
        self.assertTrue(actual.equal(video[:, :, :20, 5:25]))
        # Center crop.
        actual = uniform_crop(video, size=20, spatial_idx=1)
        self.assertTrue(actual.equal(video[:, :, 10:30, 5:25]))
        # Bottom crop.
        actual = uniform_crop(video, size=20, spatial_idx=2)
        self.assertTrue(actual.equal(video[:, :, 20:, 5:25]))

    def test_uniform_crop_with_boxes(self):
        # For videos with height < width.
        video = thwc_to_cthw(create_dummy_video_frames(20, 30, 40)).to(
            dtype=torch.float32
        )
        boxes_inp = create_random_bbox(7, 30, 40)

        # Left crop.
        actual, boxes = uniform_crop_with_boxes(
            video, size=20, spatial_idx=0, boxes=boxes_inp
        )
        self.assertTrue(actual.equal(video[:, :, 5:25, :20]))
        self._check_boxes(7, actual.shape[-2], actual.shape[-1], boxes)
        # Center crop.
        actual, boxes = uniform_crop_with_boxes(
            video, size=20, spatial_idx=1, boxes=boxes_inp
        )
        self.assertTrue(actual.equal(video[:, :, 5:25, 10:30]))
        self._check_boxes(7, actual.shape[-2], actual.shape[-1], boxes)
        # Right crop.
        actual, boxes = uniform_crop_with_boxes(
            video, size=20, spatial_idx=2, boxes=boxes_inp
        )
        self.assertTrue(actual.equal(video[:, :, 5:25, 20:]))
        self._check_boxes(7, actual.shape[-2], actual.shape[-1], boxes)

        # For videos with height > width.
        video = thwc_to_cthw(create_dummy_video_frames(20, 40, 30)).to(
            dtype=torch.float32
        )
        # Top crop.
        actual, boxes = uniform_crop_with_boxes(
            video, size=20, spatial_idx=0, boxes=boxes_inp
        )
        self.assertTrue(actual.equal(video[:, :, :20, 5:25]))
        self._check_boxes(7, actual.shape[-2], actual.shape[-1], boxes)
        # Center crop.
        actual, boxes = uniform_crop_with_boxes(
            video, size=20, spatial_idx=1, boxes=boxes_inp
        )
        self.assertTrue(actual.equal(video[:, :, 10:30, 5:25]))
        self._check_boxes(7, actual.shape[-2], actual.shape[-1], boxes)
        # Bottom crop.
        actual, boxes = uniform_crop_with_boxes(
            video, size=20, spatial_idx=2, boxes=boxes_inp
        )
        self.assertTrue(actual.equal(video[:, :, 20:, 5:25]))
        self._check_boxes(7, actual.shape[-2], actual.shape[-1], boxes)

    def test_random_crop_with_boxes(self):
        # For videos with height < width.
        video = thwc_to_cthw(create_dummy_video_frames(15, 30, 40)).to(
            dtype=torch.float32
        )
        boxes_inp = create_random_bbox(7, 30, 40)

        actual, boxes = random_crop_with_boxes(video, size=20, boxes=boxes_inp)
        self.assertEqual(actual.shape, (3, 15, 20, 20))
        self._check_boxes(7, actual.shape[2], actual.shape[3], boxes)

    def test_uniform_crop_transform(self):
        video = thwc_to_cthw(create_dummy_video_frames(10, 30, 40)).to(
            dtype=torch.float32
        )
        test_clip = {"video": video, "aug_index": 1, "label": 0}

        transform = UniformCropVideo(20)

        actual = transform(test_clip)
        c, t, h, w = actual["video"].shape
        self.assertEqual(c, 3)
        self.assertEqual(t, 10)
        self.assertEqual(h, 20)
        self.assertEqual(w, 20)
        self.assertTrue(actual["video"].equal(video[:, :, 5:25, 10:30]))

    def test_clip_boxes(self):
        boxes_inp = create_random_bbox(7, 40, 80)
        clipped_boxes = clip_boxes_to_image(boxes_inp, 20, 40)
        self._check_boxes(7, 20, 40, clipped_boxes)

    def test_horizontal_flip_with_boxes(self):
        video = thwc_to_cthw(create_dummy_video_frames(10, 20, 40)).to(
            dtype=torch.float32
        )
        boxes_inp = create_random_bbox(7, 20, 40)

        actual, boxes = horizontal_flip_with_boxes(0.0, video, boxes_inp)
        self.assertTrue(actual.equal(video))
        self.assertTrue(boxes.equal(boxes_inp))

        actual, boxes = horizontal_flip_with_boxes(1.0, video, boxes_inp)
        self.assertEqual(actual.shape, video.shape)
        self._check_boxes(7, actual.shape[-2], actual.shape[-1], boxes)
        self.assertTrue(actual.flip((-1)).equal(video))

    def test_normalize(self):
        video = thwc_to_cthw(create_dummy_video_frames(10, 30, 40)).to(
            dtype=torch.float32
        )
        transform = Normalize(video.mean(), video.std())

        actual = transform(video)
        self.assertAlmostEqual(actual.mean().item(), 0)
        self.assertAlmostEqual(actual.std().item(), 1)

    def test_convert_to_one_hot(self):
        # Test without label smooth.
        num_class = 5
        num_samples = 10
        labels = torch.arange(0, num_samples) % num_class
        one_hot = convert_to_one_hot(labels, num_class)
        self.assertEqual(one_hot.sum(), num_samples)
        label_value = 1.0
        for index in range(num_samples):
            label = labels[index]

            self.assertEqual(one_hot[index][label], label_value)

        # Test with label smooth.
        labels = torch.arange(0, num_samples) % num_class
        label_smooth = 0.1
        one_hot_smooth = convert_to_one_hot(
            labels, num_class, label_smooth=label_smooth
        )
        self.assertEqual(one_hot_smooth.sum(), num_samples)
        label_value_smooth = 1 - label_smooth + label_smooth / num_class
        for index in range(num_samples):
            label = labels[index]
            self.assertEqual(one_hot_smooth[index][label], label_value_smooth)

    def test_OpSampler(self):
        # Test with weights.
        n_transform = 3
        transform_list = [lambda x, i=i: x.fill_(i) for i in range(n_transform)]
        transform_weight = [1] * n_transform
        transform = OpSampler(transform_list, transform_weight)
        input_tensor = torch.rand(1)
        out_tensor = transform(input_tensor)
        self.assertTrue(out_tensor.sum() in list(range(n_transform)))

        # Test without weights.
        input_tensor = torch.rand(1)
        transform_no_weight = OpSampler(transform_list)
        out_tensor = transform_no_weight(input_tensor)
        self.assertTrue(out_tensor.sum() in list(range(n_transform)))

        # Make sure each transform is sampled without replacement.
        transform_op_values = [3, 5, 7]
        all_possible_out = [15, 21, 35]

        transform_list = [lambda x, i=i: x * i for i in transform_op_values]
        test_time = 100
        transform_no_replacement = OpSampler(transform_list, num_sample_op=2)
        for _ in range(test_time):
            input_tensor = torch.ones(1)
            out_tensor = transform_no_replacement(input_tensor)
            self.assertTrue(out_tensor.sum() in all_possible_out)

        # Make sure each transform is sampled with replacement.
        transform_op_values = [3, 5, 7]
        possible_replacement_out = [9, 25, 49]
        input_tensor = torch.ones(1)
        transform_list = [lambda x, i=i: x * i for i in transform_op_values]
        test_time = 100
        transform_no_replacement = OpSampler(
            transform_list, replacement=True, num_sample_op=2
        )
        replace_time = 0
        for _ in range(test_time):
            input_tensor = torch.ones(1)
            out_tensor = transform_no_replacement(input_tensor)
            if out_tensor.sum() in possible_replacement_out:
                replace_time += 1
        self.assertTrue(replace_time > 0)

        # Test without weights.
        transform_op_values = [3.0, 5.0, 7.0]
        input_tensor = torch.ones(1)
        transform_list = [lambda x, i=i: x * i for i in transform_op_values]
        test_time = 10000
        weights = [10.0, 2.0, 1.0]
        transform_no_replacement = OpSampler(transform_list, weights)
        weight_counter = Counter()
        for _ in range(test_time):
            input_tensor = torch.ones(1)
            out_tensor = transform_no_replacement(input_tensor)
            weight_counter[out_tensor.sum().item()] += 1

        for index, w in enumerate(weights):
            gt_dis = w / sum(weights)
            out_key = transform_op_values[index]
            self.assertTrue(
                np.allclose(weight_counter[out_key] / test_time, gt_dis, rtol=0.2)
            )

    def test_mixup(self):
        # Test images.
        batch_size = 2
        h_size = 10
        w_size = 10
        c_size = 3
        input_images = torch.rand(batch_size, c_size, h_size, w_size)
        input_images[0, :].fill_(0)
        input_images[1, :].fill_(1)
        alpha = 1.0
        label_smoothing = 0.0
        num_classes = 5
        transform_mixup = MixUp(
            alpha=alpha,
            label_smoothing=label_smoothing,
            num_classes=num_classes,
        )
        labels = torch.arange(0, batch_size) % num_classes
        mixed_images, mixed_labels = transform_mixup(input_images, labels)
        gt_image_sum = h_size * w_size * c_size
        label_sum = batch_size

        self.assertTrue(
            np.allclose(mixed_images.sum().item(), gt_image_sum, rtol=0.001)
        )
        self.assertTrue(np.allclose(mixed_labels.sum().item(), label_sum, rtol=0.001))
        self.assertEqual(mixed_labels.size(0), batch_size)
        self.assertEqual(mixed_labels.size(1), num_classes)

        # Test videos.
        batch_size = 2
        h_size = 10
        w_size = 10
        c_size = 3
        t_size = 2
        input_video = torch.rand(batch_size, c_size, t_size, h_size, w_size)
        input_video[0, :].fill_(0)
        input_video[1, :].fill_(1)
        alpha = 1.0
        label_smoothing = 0.0
        num_classes = 5
        transform_mixup = MixUp(
            alpha=alpha,
            label_smoothing=label_smoothing,
            num_classes=num_classes,
        )
        labels = torch.arange(0, batch_size) % num_classes
        mixed_videos, mixed_labels = transform_mixup(input_video, labels)
        gt_video_sum = h_size * w_size * c_size * t_size
        label_sum = batch_size

        self.assertTrue(
            np.allclose(mixed_videos.sum().item(), gt_video_sum, rtol=0.001)
        )
        self.assertTrue(np.allclose(mixed_labels.sum().item(), label_sum, rtol=0.001))
        self.assertEqual(mixed_labels.size(0), batch_size)
        self.assertEqual(mixed_labels.size(1), num_classes)

        # Test videos with label smoothing.
        input_video = torch.rand(batch_size, c_size, t_size, h_size, w_size)
        input_video[0, :].fill_(0)
        input_video[1, :].fill_(1)
        alpha = 1.0
        label_smoothing = 0.2
        num_classes = 5
        transform_mixup = MixUp(
            alpha=alpha,
            label_smoothing=label_smoothing,
            num_classes=num_classes,
        )
        labels = torch.arange(0, batch_size) % num_classes
        mixed_videos, mixed_labels = transform_mixup(input_video, labels)
        gt_video_sum = h_size * w_size * c_size * t_size
        label_sum = batch_size
        self.assertTrue(
            np.allclose(mixed_videos.sum().item(), gt_video_sum, rtol=0.001)
        )
        self.assertTrue(np.allclose(mixed_labels.sum().item(), label_sum, rtol=0.001))
        self.assertEqual(mixed_labels.size(0), batch_size)
        self.assertEqual(mixed_labels.size(1), num_classes)

        # Check the smoothing value is in label.
        smooth_value = label_smoothing / num_classes
        self.assertTrue(smooth_value in torch.unique(mixed_labels))

    def test_cutmix(self):
        torch.manual_seed(0)
        # Test images.
        batch_size = 2
        h_size = 10
        w_size = 10
        c_size = 3
        input_images = torch.rand(batch_size, c_size, h_size, w_size)
        input_images[0, :].fill_(0)
        input_images[1, :].fill_(1)
        alpha = 1.0
        label_smoothing = 0.0
        num_classes = 5
        transform_cutmix = CutMix(
            alpha=alpha,
            label_smoothing=label_smoothing,
            num_classes=num_classes,
        )
        labels = torch.arange(0, batch_size) % num_classes
        mixed_images, mixed_labels = transform_cutmix(input_images, labels)
        gt_image_sum = h_size * w_size * c_size
        label_sum = batch_size

        self.assertTrue(
            np.allclose(mixed_images.sum().item(), gt_image_sum, rtol=0.001)
        )
        self.assertTrue(np.allclose(mixed_labels.sum().item(), label_sum, rtol=0.001))
        self.assertEqual(mixed_labels.size(0), batch_size)
        self.assertEqual(mixed_labels.size(1), num_classes)

        # Test videos.
        batch_size = 2
        h_size = 10
        w_size = 10
        c_size = 3
        t_size = 2
        input_video = torch.rand(batch_size, c_size, t_size, h_size, w_size)
        input_video[0, :].fill_(0)
        input_video[1, :].fill_(1)
        alpha = 1.0
        label_smoothing = 0.0
        num_classes = 5
        transform_cutmix = CutMix(
            alpha=alpha,
            label_smoothing=label_smoothing,
            num_classes=num_classes,
        )
        labels = torch.arange(0, batch_size) % num_classes
        mixed_videos, mixed_labels = transform_cutmix(input_video, labels)
        gt_video_sum = h_size * w_size * c_size * t_size
        label_sum = batch_size

        self.assertTrue(
            np.allclose(mixed_videos.sum().item(), gt_video_sum, rtol=0.001)
        )
        self.assertTrue(np.allclose(mixed_labels.sum().item(), label_sum, rtol=0.001))
        self.assertEqual(mixed_labels.size(0), batch_size)
        self.assertEqual(mixed_labels.size(1), num_classes)

        # Test videos with label smoothing.
        input_video = torch.rand(batch_size, c_size, t_size, h_size, w_size)
        input_video[0, :].fill_(0)
        input_video[1, :].fill_(1)
        alpha = 1.0
        label_smoothing = 0.2
        num_classes = 5
        transform_cutmix = CutMix(
            alpha=alpha,
            label_smoothing=label_smoothing,
            num_classes=num_classes,
        )
        labels = torch.arange(0, batch_size) % num_classes
        mixed_videos, mixed_labels = transform_cutmix(input_video, labels)
        gt_video_sum = h_size * w_size * c_size * t_size
        label_sum = batch_size
        self.assertTrue(
            np.allclose(mixed_videos.sum().item(), gt_video_sum, rtol=0.001)
        )
        self.assertTrue(np.allclose(mixed_labels.sum().item(), label_sum, rtol=0.001))
        self.assertEqual(mixed_labels.size(0), batch_size)
        self.assertEqual(mixed_labels.size(1), num_classes)

        # Check the smoothing value is in label.
        smooth_value = label_smoothing / num_classes
        self.assertTrue(smooth_value in torch.unique(mixed_labels))

        # Check cutmixed video has both 0 and 1.
        # Run 20 times to avoid rare cases where the random box is empty.
        test_times = 20
        seen_all_value1 = False
        seen_all_value2 = False
        for _ in range(test_times):
            mixed_videos, mixed_labels = transform_cutmix(input_video, labels)
            if 0 in mixed_videos[0, :] and 1 in mixed_videos[0, :]:
                seen_all_value1 = True

            if 0 in mixed_videos[1, :] and 1 in mixed_videos[1, :]:
                seen_all_value2 = True

            if seen_all_value1 and seen_all_value2:
                break
        self.assertTrue(seen_all_value1)
        self.assertTrue(seen_all_value2)

    def _check_boxes(self, num_boxes, height, width, boxes):
        self.assertEqual(boxes.shape, (num_boxes, 4))
        self.assertTrue(boxes[:, [0, 2]].min() >= 0 and boxes[:, [0, 2]].max() < width)
        self.assertTrue(boxes[:, [1, 3]].min() >= 0 and boxes[:, [1, 3]].max() < height)
        
    def test_randaug(self):
        # Test default RandAugment.
        t, c, h, w = 8, 3, 200, 200
        test_time = 20
        video_tensor = torch.rand(t, c, h, w)
        video_rand_aug_fn = RandAugment()
        for _ in range(test_time):
            video_tensor_aug = video_rand_aug_fn(video_tensor)
            self.assertTrue(video_tensor.size() == video_tensor_aug.size())
            self.assertTrue(video_tensor.dtype == video_tensor_aug.dtype)
            # Make sure the video is in range.
            self.assertTrue(video_tensor_aug.max().item() <= 1)
            self.assertTrue(video_tensor_aug.min().item() >= 0)

        # Test RandAugment with uniform sampling.
        t, c, h, w = 8, 3, 200, 200
        test_time = 20
        video_tensor = torch.rand(t, c, h, w)
        video_rand_aug_fn = RandAugment(sampling_type="uniform")
        for _ in range(test_time):
            video_tensor_aug = video_rand_aug_fn(video_tensor)
            self.assertTrue(video_tensor.size() == video_tensor_aug.size())
            self.assertTrue(video_tensor.dtype == video_tensor_aug.dtype)
            # Make sure the video is in range.
            self.assertTrue(video_tensor_aug.max().item() <= 1)
            self.assertTrue(video_tensor_aug.min().item() >= 0)

        # Test if default fill color if found.
        # Test multiple times due to randomness.
        t, c, h, w = 8, 3, 200, 200
        test_time = 40
        video_tensor = torch.ones(t, c, h, w)
        video_rand_aug_fn = RandAugment(
            num_layers=1,
            prob=1,
            sampling_type="gaussian",
        )
        found_fill_color = 0
        for _ in range(test_time):
            video_tensor_aug = video_rand_aug_fn(video_tensor)
            if 0.5 in video_tensor_aug:
                found_fill_color += 1
        self.assertTrue(found_fill_color >= 1)
