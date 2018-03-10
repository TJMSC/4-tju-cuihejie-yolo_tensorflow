import tensorflow as tf
import tensorflow.contrib.slim as slim
import numpy as np

import config as cfg


class Yolo(object):

    def __init__(self):
        self.coord_scale = cfg.COORD_SCALE
        self.noobj_scale = cfg.NOOBJ_SCALE

        self.images = tf.placeholder(tf.float32, [cfg.BATCH_SIZE, cfg.IMAGE_SIZE, cfg.IMAGE_SIZE, 3], name='images')
        self.labels = tf.placeholder(tf.float32, [cfg.BATCH_SIZE, cfg.CELL_SIZE, cfg.CELL_SIZE, 5 + cfg.CLASS_NUM],
                                     name='labels')
        self.net = self._build_net(self.images, cfg.CLASS_NUM, cfg.BOX_PER_CELL, cfg.CELL_SIZE)
        self.loss = self._loss(self.net, self.labels)

    def inference(self, images, class_num, boxes_per_cell, cell_num,
                  keep_probability, phase_train=True, reuse=None):
        batch_norm_params = {
            # Decay for the moving averages.
            'decay': 0.995,
            # epsilon to prevent 0s in variance.
            'epsilon': 0.001,
            # force in-place updates of mean and variance estimates
            'updates_collections': None,
            # Moving averages ends up in the trainable variables collection
            'variables_collections': [tf.GraphKeys.TRAINABLE_VARIABLES],
        }

        with slim.arg_scope([slim.conv2d, slim.fully_connected],
                            weights_initializer=tf.truncated_normal_initializer(stddev=0.1),
                            weights_regularizer=slim.l2_regularizer(0.005),
                            normalizer_fn=slim.batch_norm,
                            normalizer_params=batch_norm_params):
            return self._build_net(images, class_num, boxes_per_cell, cell_num,
                                   is_training=phase_train, dropout_keep_prob=keep_probability, reuse=reuse)

    def _calc_iou(self, box1, box2):
        """
        box: [BATCH_SIZE, CELL_SIZE, CELL_SIZE, 5*BOX_PER_CELL]
        5  : [c, x, y, w, h]
        """

        # x_index = np.arange(1, 5 * cfg.BOX_PER_CELL, 5)
        # y_index = np.arange(2, 5 * cfg.BOX_PER_CELL, 5)
        # w_index = np.arange(3, 5 * cfg.BOX_PER_CELL, 5)
        # h_index = np.arange(4, 5 * cfg.BOX_PER_CELL, 5)

        c_area = box1[..., 3:5 * cfg.BOX_PER_CELL:5] * box1[..., 4:5 * cfg.BOX_PER_CELL:5]
        g_area = box2[..., 3:5 * cfg.BOX_PER_CELL:5] * box2[..., 4:5 * cfg.BOX_PER_CELL:5]

        box1 = tf.stack([[box1[..., 1:5 * cfg.BOX_PER_CELL:5] - box1[..., 3:5 * cfg.BOX_PER_CELL:5] / 2.0],  # x1
                         [box1[..., 2:5 * cfg.BOX_PER_CELL:5] - box1[..., 4:5 * cfg.BOX_PER_CELL:5] / 2.0],  # y1
                         [box1[..., 1:5 * cfg.BOX_PER_CELL:5] + box1[..., 3:5 * cfg.BOX_PER_CELL:5] / 2.0],  # x2
                         [box1[..., 2:5 * cfg.BOX_PER_CELL:5] + box1[..., 4:5 * cfg.BOX_PER_CELL:5] / 2.0]],
                         axis=0)  # y2
        box1 = tf.squeeze(box1, [1])

        box2 = tf.stack([[box2[..., 1:5 * cfg.BOX_PER_CELL:5] - box2[..., 3:5 * cfg.BOX_PER_CELL:5] / 2.0],  # x1
                         [box2[..., 2:5 * cfg.BOX_PER_CELL:5] - box2[..., 4:5 * cfg.BOX_PER_CELL:5] / 2.0],  # y1
                         [box2[..., 1:5 * cfg.BOX_PER_CELL:5] + box2[..., 3:5 * cfg.BOX_PER_CELL:5] / 2.0],  # x2
                         [box2[..., 2:5 * cfg.BOX_PER_CELL:5] + box2[..., 4:5 * cfg.BOX_PER_CELL:5] / 2.0]])  # y2
        box2 = tf.squeeze(box2, [1])

        left_top = tf.maximum(box1[:2, ...], box2[:2, ...])
        right_bottom = tf.minimum(box1[2:, ...], box2[2:, ...])

        w = tf.maximum(0.0, right_bottom[0, ...] - left_top[0, ...])
        h = tf.maximum(0.0, right_bottom[1, ...] - left_top[1, ...])
        area = w * h

        iou = area / (c_area + g_area - area)

        return iou

    def _build_net(self, inputs, class_num, boxes_per_cell, cell_num,
                   is_training=True,
                   dropout_keep_prob=0.8,
                   reuse=None,
                   scope='yolo_v1'):
        with tf.variable_scope(scope, 'yolo_v1', [inputs], reuse=reuse):
            with slim.arg_scope([slim.batch_norm, slim.dropout],
                                is_training=is_training):
                with slim.arg_scope([slim.conv2d],
                                    activation_fn=tf.nn.leaky_relu), slim.arg_scope([slim.max_pool2d], padding='SAME'):
                    net = slim.conv2d(inputs, 64, 7, 2, scope='conv_1')
                    net = slim.max_pool2d(net, 2, scope='pool_2')
                    net = slim.conv2d(net, 192, 3, scope='conv_3')
                    net = slim.max_pool2d(net, 2, scope='pool_4')
                    net = slim.conv2d(net, 128, 1, scope='conv_5')
                    net = slim.conv2d(net, 256, 3, scope='conv_6')
                    net = slim.conv2d(net, 256, 1, scope='conv_7')
                    net = slim.conv2d(net, 512, 3, scope='conv_8')
                    net = slim.max_pool2d(net, 2, scope='pool_9')
                    net = slim.conv2d(net, 256, 1, scope='conv_10')
                    net = slim.conv2d(net, 512, 3, scope='conv_11')
                    net = slim.conv2d(net, 256, 1, scope='conv_12')
                    net = slim.conv2d(net, 512, 3, scope='conv_13')
                    net = slim.conv2d(net, 256, 1, scope='conv_14')
                    net = slim.conv2d(net, 512, 3, scope='conv_15')
                    net = slim.conv2d(net, 256, 1, scope='conv_16')
                    net = slim.conv2d(net, 512, 3, scope='conv_17')
                    net = slim.conv2d(net, 512, 1, scope='conv_18')
                    net = slim.conv2d(net, 1024, 3, scope='conv_19')
                    net = slim.max_pool2d(net, 2, scope='pool_20')
                    net = slim.conv2d(net, 512, 1, scope='conv_21')
                    net = slim.conv2d(net, 1024, 3, scope='conv_22')
                    net = slim.conv2d(net, 512, 1, scope='conv_23')
                    net = slim.conv2d(net, 1024, 3, scope='conv_24')
                    net = slim.conv2d(net, 1024, 3, scope='conv_25')
                    net = slim.conv2d(net, 1024, 3, stride=2, scope='conv_26')
                    net = slim.conv2d(net, 1024, 3, scope='conv_27')
                    net = slim.conv2d(net, 1024, 3, scope='conv_28')

                net = slim.flatten(net, scope="flatten_29")

                with slim.arg_scope([slim.fully_connected], activation_fn=tf.nn.leaky_relu,
                                    weights_regularizer=slim.l2_regularizer(0.001)):
                    net = slim.fully_connected(net, 4096, scope='conn_30')
                    net = slim.dropout(net, scope="dropout_31", keep_prob=dropout_keep_prob)
                net = slim.fully_connected(net, cell_num * cell_num * (class_num + 5 * boxes_per_cell), scope="conn_32")
                net = tf.reshape(net, [tf.shape(net)[0], cell_num, cell_num, class_num + 5 * boxes_per_cell])

        return net

    def _loss(self, preds, labels):
        """ Get the train op

        Args:
            preds:  [BATCH_SIZE, CELL_SIZE, CELL_SIZE, 5 * BOX_PER_CELL + CLASS_NUM]
            labels: [BATCH_SIZE, CELL_SIZE, CELL_SIZE, 5 + CLASS_NUM]

        Returns:

        """

        mask_obj = labels[:, :, :, 0, tf.newaxis]  # [?, CELL_SIZE, CELL_SIZE]
        mask_obj = tf.tile(mask_obj, [1, 1, 1, cfg.BOX_PER_CELL])

        boxes = tf.tile(labels[..., :5], [1, 1, 1, cfg.BOX_PER_CELL])  # [?, CELL_SIZE, CELL_SIZE, 5 * BOX_PER_CELL]

        iou = self._calc_iou(preds[:, :, :, :5 * cfg.BOX_PER_CELL], boxes[:, :, :, :5 * cfg.BOX_PER_CELL])

        max_iou = tf.reduce_max(iou, [3], keepdims=True)

        response = tf.cast(iou > max_iou, tf.float32)

        # Compute first line
        # x_index = np.arange(1, 5 * cfg.BOX_PER_CELL, 5)
        # y_index = np.arange(2, 5 * cfg.BOX_PER_CELL, 5)
        coord_loss = cfg.COORD_SCALE * tf.reduce_sum(
            mask_obj * response * (
                    tf.square(preds[..., 1:5*cfg.BOX_PER_CELL:5] - boxes[..., 1:5*cfg.BOX_PER_CELL:5]) +
                    tf.square(preds[..., 2:5*cfg.BOX_PER_CELL:5] - boxes[..., 2:5*cfg.BOX_PER_CELL:5])
            )
        )
        tf.losses.add_loss(coord_loss)

        # Compute second line
        # w_index = np.arange(3, 5 * cfg.BOX_PER_CELL, 5)
        # h_index = np.arange(4, 5 * cfg.BOX_PER_CELL, 5)
        size_loss = cfg.COORD_SCALE * tf.reduce_sum(
            mask_obj * response * (
                tf.square(tf.sqrt(preds[..., 3:5*cfg.BOX_PER_CELL:5]) - tf.sqrt(boxes[..., 3:5*cfg.BOX_PER_CELL:5])) +
                tf.square(tf.sqrt(preds[..., 4:5*cfg.BOX_PER_CELL:5]) - tf.sqrt(boxes[..., 4:5*cfg.BOX_PER_CELL:5]))
                )
        )
        tf.losses.add_loss(size_loss)

        # Compute third line
        # c_index = np.arange(0, 5 * cfg.BOX_PER_CELL, 5)
        obj_loss = tf.reduce_sum(
            mask_obj * response * tf.square(preds[..., 0:5*cfg.BOX_PER_CELL:5] - iou)
        )
        tf.losses.add_loss(obj_loss)

        # Compute forth line
        noobj_loss = cfg.NOOBJ_SCALE * tf.reduce_sum(
            (1 - mask_obj) * tf.square(preds[..., 0:5*cfg.BOX_PER_CELL:5] - 0)
        )
        tf.losses.add_loss(noobj_loss)

        # Compute fifth line
        class_loss = tf.reduce_sum(
            mask_obj * tf.reduce_sum(tf.square(preds[..., -cfg.CLASS_NUM:] - labels[..., -cfg.CLASS_NUM:]))
        )
        tf.losses.add_loss(class_loss)

        return tf.losses.get_total_loss()
