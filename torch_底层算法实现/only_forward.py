# Author: Jintao Huang
# Time: 2020-5-17

# 为防止与torch中的函数搞混，自己实现的函数前会加上 `_`
import torch
import torch.nn.functional as F
from torch import Tensor
from typing import Tuple


# --------------------------------------------------- activation

def _relu(x: Tensor) -> Tensor:
    """(F.relu()) - 已重写简化

    :param x: shape = (N, In) or (N, Cin, H, W)
    :return: shape = x.shape"""
    return torch.where(x > 0, x, torch.tensor(0.))
    # or:
    # return x * (x > 0).float()


def _leaky_relu(x: Tensor, negative_slope: float = 0.01) -> Tensor:
    """(F.leaky_relu()) - 已重写简化"""
    return torch.where(x > 0, x, negative_slope * x)


def _sigmoid(x: Tensor) -> Tensor:
    """sigmoid(F.sigmoid()) - 已重写简化"""

    return 1 / (1 + torch.exp(-x))


def _tanh(x: Tensor) -> Tensor:
    """(F.tanh()) - 已重写简化"""
    return (torch.exp(2 * x) - 1) / (torch.exp(2 * x) + 1)
    # or:
    # return (torch.exp(x) - torch.exp(-x)) / (torch.exp(x) + torch.exp(-x))


def _softmax(x: Tensor, dim: int) -> Tensor:
    """softmax(F.softmax()) - 已重写简化

    :param x: shape = (N, In)
    :param dim: int. 一般dim设为-1(表示输出Tensor的和为1.的dim为哪个)
    :return: shape = x.shape"""
    # shape(N, In) / shape(N, 1), 若dim = -1
    return torch.exp(x) / torch.sum(torch.exp(x), dim, True)


# --------------------------------------------------- loss

def to_categorical(x: Tensor, num_classes: int) -> Tensor:
    """转热码 - 已重写简化

    :param x: shape = (...). int
    :param num_classes: int. 分类数
    :return: shape = (..., num_classes). float32"""

    return torch.eye(num_classes, dtype=torch.float, device=x.device)[x]


def _cross_entropy(y_pred: Tensor, y_true: Tensor) -> Tensor:
    """交叉熵损失函数(F.cross_entropy()). y_pred 未过softmax

    :param y_pred: shape = (N, num_classes)
    :param y_true: shape = (N,)
    :return: shape = ()"""

    y_pred = torch.clamp_min(torch.softmax(y_pred, dim=-1), 1e-6)  # 防log(0)
    y_true = to_categorical(y_true, y_pred.shape[-1])

    return torch.mean(torch.sum(y_true * -torch.log(y_pred), -1))


def _binary_cross_entropy(y_pred, y_true, with_logits=False):
    """交叉熵损失函数(F.binary_cross_entropy() and F.binary_cross_entropy_with_logits())

    :param y_pred: shape = (N,)
    :param y_true: shape = (N,)
    :param with_logits: y_pred是否未过sigmoid
    :return: shape = ()"""

    assert y_pred.dtype in (torch.float32, torch.float64)
    if with_logits:
        y_pred = torch.sigmoid(y_pred)
    # 此处不检查y_pred 要在 [0., 1.] 区间内
    y_pred = torch.clamp(y_pred, 1e-6, 1 - 1e-6)
    # 前式与后式关于0.5对称(The former and the latter are symmetric about 0.5)
    return torch.mean(y_true * -torch.log(y_pred) + (1 - y_true) * -torch.log(1 - y_pred))


def _mse_loss(y_pred, y_true):
    """均方误差损失(F.mse_loss() 只实现了部分功能)

    :param y_pred: shape = (N, num) or (...)
    :param y_true: shape = (N, num) or (...)
    :return: shape = ()"""

    return torch.mean((y_true - y_pred) ** 2)


# --------------------------------------------------- layers
def _batch_norm(x: Tensor, running_mean: Tensor, running_var: Tensor, weight: Tensor, bias: Tensor,
                training: bool = False, momentum: float = 0.1, eps: float = 1e-5) -> Tensor:
    """BN(F.batch_norm()) - 已重写简化

    :param x: shape = (N, In) or (N, Cin, H, W)
    :param running_mean: shape = (In,) 或 (Cin,) 下同
    :param running_var: shape = (In,)
    :param weight: shape = (In,)
    :param bias: shape = (In,)
    :param momentum: (同torch)动量实际为 1 - momentum
    :return: shape = x.shape"""

    if training:
        if x.dim() == 2:
            _dim = (0,)
        elif x.dim() == 4:
            _dim = (0, 2, 3)
        else:
            raise ValueError("x dim error")
        mean = torch.mean(x, _dim)  # 总体 = 估计
        eval_var = torch.var(x, _dim, unbiased=True)  # 无偏估计, x作为样本
        var = torch.var(x, _dim, unbiased=False)  # 用于标准化, x作为总体
        running_mean[:] = (1 - momentum) * running_mean + momentum * mean
        running_var[:] = (1 - momentum) * running_var + momentum * eval_var  # 无偏估计
    else:
        mean = running_mean
        var = running_var
    # 2D时, mean.shape = (In,)
    # 4D时, mean.shape = (Cin, 1, 1)
    if x.dim() == 4:  # 扩维
        mean, var = mean[:, None, None], var[:, None, None]
        weight, bias = weight[:, None, None], bias[:, None, None]
    return (x - mean) * torch.rsqrt(var + eps) * weight + bias
    # or: 以下为torch中源码实现方式
    # scale = weight * torch.rsqrt(var + eps)
    # bias = bias - mean * scale
    # return x * scale + bias


def _dropout(x, drop_p, training):
    """(torch.dropout()).
    notice: 如果是`not training` / `not drop_p`: 返回引用. 如果training: 返回new的tensor

    :param x: shape = (N, In)
    :return: shape = x.shape"""

    if not training or not drop_p:
        return x

    keep_p = 1 - drop_p
    keep_tensors = torch.floor(keep_p + torch.rand(x.shape, dtype=x.dtype, device=x.device))

    return x / keep_p * keep_tensors  # 只有该步会反向传播


def _zero_padding2d(x: Tensor, padding: int) -> Tensor:
    """零填充(F.pad()) - 已重写简化

    :param x: shape = (N, Cin, Hin, Win)
    :param padding: int
    :return: shape = (N, Cin, Hout, Wout)"""

    output = torch.zeros((*x.shape[:2],  # N, Cin
                          x.shape[-2] + 2 * padding,  # Hout
                          x.shape[-1] + 2 * padding), dtype=x.dtype, device=x.device)  # Wout
    h_out, w_out = output.shape[-2:]
    output[:, :, padding:h_out - padding, padding:w_out - padding] = x
    return output


def _max_pool2d(x, kernel_size, stride=None, padding=0, dilation=1, ceil_mode=False):
    """最大池化(F.max_pool2d()).
    notice: padding的0.不加入求max()运算

    :param x: shape = (N, Cin, Hin, Win) or (Cin, Hin, Win). 不允许2D
    :param kernel_size: Union[int, tuple(H, W)]
    :param stride: strides: Union[int, tuple(H, W)] = pool_size
    :param padding: Union[int, tuple(H, W)]
    :param .dilation: 未实现.
    :param .ceil_mode: 未实现.
    :return: shape = (B, Cin, Hout, Wout)"""

    assert x.dim() in (3, 4)
    if isinstance(kernel_size, int):
        kernel_size = kernel_size, kernel_size
    stride = stride or kernel_size
    if isinstance(stride, int):
        stride = stride, stride
    if isinstance(padding, int):
        padding = padding, padding

    # Out(H, W) = (In(H, W) + 2 * padding − kernel_size) // stride + 1
    output = torch.empty((*x.shape[:-2],
                          (x.shape[-2] + 2 * padding[0] - kernel_size[0]) // stride[0] + 1,  # Hout
                          (x.shape[-1] + 2 * padding[1] - kernel_size[1]) // stride[1] + 1),  # Wout
                         dtype=x.dtype, device=x.device)
    # ---------------- 算法
    for i in range(output.shape[-2]):
        for j in range(output.shape[-1]):
            h_start, w_start = i * stride[0] - padding[0], j * stride[1] - padding[1]
            # h_start, w_start < 0. 会报错
            h_pos, w_pos = slice(h_start if h_start >= 0 else 0, (h_start + kernel_size[0])), \
                           slice(w_start if w_start >= 0 else 0, (w_start + kernel_size[1]))
            output[..., i, j] = torch.max(torch.max(x[..., h_pos, w_pos], dim=-2)[0], dim=-1)[0]  # dim=(-2, -1)
    return output


def _avg_pool2d(x, kernel_size, stride=None, padding=0, dilation=1, ceil_mode=False):
    """平均池化(F.avg_pool2d()).
    notice: padding的0.加入求mean()运算

    :param x: shape = (N, Cin, Hin, Win) or (Cin, Hin, Win). 不允许2D
    :param kernel_size: Union[int, tuple(H, W)]
    :param stride: strides: Union[int, tuple(H, W)] = pool_size
    :param padding: Union[int, tuple(H, W)]
    :param .dilation: 未实现.
    :param .ceil_mode: 未实现.
    :return: shape = (B, Cin, Hout, Wout)"""

    assert x.dim() in (3, 4)
    if isinstance(kernel_size, int):
        kernel_size = kernel_size, kernel_size
    stride = stride or kernel_size
    if isinstance(stride, int):
        stride = stride, stride

    # 这里与max_pool2d 有很大区别，avg_pool2d 计算要和pad的0. 一起求平均
    if isinstance(padding, int):
        padding = padding, padding, padding, padding
    else:
        padding = padding[1], padding[1], padding[0], padding[0]
    if padding:
        x = F.pad(x, padding)

    # Out(H, W) = (In(H, W) + 2 * padding − kernel_size) // stride + 1
    output = torch.empty((*x.shape[:-2],
                          (x.shape[-2] - kernel_size[0]) // stride[0] + 1,  # Hout (x已加上padding)
                          (x.shape[-1] - kernel_size[1]) // stride[1] + 1),  # Wout
                         dtype=x.dtype, device=x.device)
    # ---------------- 算法
    for i in range(output.shape[-2]):
        for j in range(output.shape[-1]):
            h_start, w_start = i * stride[0], j * stride[1]
            # h_start, w_start 一定 >= 0
            h_pos, w_pos = slice(h_start, (h_start + kernel_size[0])), \
                           slice(w_start, (w_start + kernel_size[1]))
            output[..., i, j] = torch.mean(x[..., h_pos, w_pos], dim=(-2, -1))
    return output


def _linear(x: Tensor, weight: Tensor, bias: Tensor = None) -> Tensor:
    """全连接层(F.linear()) - 已重写简化

    :param x: shape = (N, In)
    :param weight: shape = (Out, In)
    :param bias: shape = (Out,)
    :return: shape = (N, Out)"""

    return x @ weight.t() + bias if bias is not None else 0.


def _conv2d(x: Tensor, weight: Tensor, bias: Tensor = None, stride: int = 1, padding: int = 0) -> Tensor:
    """2d卷积(F.conv2d()) - 已重写简化

    :param x: shape = (N, Cin, Hin, Win)
    :param weight: shape = (Cout, Cin, KH, KW)
    :param bias: shape = (Cout,)
    :param stride: int
    :param padding: int
    :return: shape = (N, Cout, Hout, Wout)
    """
    if padding:
        x = _zero_padding2d(x, padding)
    kernel_size = weight.shape[-2:]
    # Out(H, W) = (In(H, W) + 2 * padding − kernel_size) // stride + 1
    output_h, output_w = (x.shape[2] - kernel_size[0]) // stride + 1, \
                         (x.shape[3] - kernel_size[1]) // stride + 1
    output = torch.empty((x.shape[0], weight.shape[0], output_h, output_w),
                         dtype=x.dtype, device=x.device)
    for i in range(output.shape[2]):  # Hout
        for j in range(output.shape[3]):  # # Wout
            h_start, w_start = i * stride, j * stride
            h_pos, w_pos = slice(h_start, (h_start + kernel_size[0])), \
                           slice(w_start, (w_start + kernel_size[1]))

            output[:, :, i, j] = torch.sum(
                # N, K_Cout, K_Cin, KH, KW
                x[:, None, :, h_pos, w_pos] * weight[None, :, :, :, :], dim=(-3, -2, -1)) \
                                 + (bias if bias is not None else 0)
    return output


def _nearest_interpolate(x: Tensor, size: Tuple[int, int] = None, scale_factor: float = None) -> Tensor:
    """最近邻插值(F.interpolate(mode="nearest")). 与torch实现相同，与cv实现是否相同未知 - 已重写简化

    :param x: shape = (N, C, Hin, Win) - 像素点当作点来看待(与bilinear不同)
    :param size: Tuple[Hout, Wout]
    :param scale_factor: size和scale_factor必须且只能提供其中的一个参数
    :return: shape = (N, C, Hout, Wout)
    """
    in_size = x.shape[-2:]
    if scale_factor:
        size = int(in_size[0] * scale_factor), int(in_size[1] * scale_factor)  # out_size
    step_h, step_w = in_size[0] / size[0], in_size[1] / size[1]  # 步长
    axis_h = torch.arange(0, in_size[0], step_h, device=x.device).long()  # h坐标轴 floor
    axis_w = torch.arange(0, in_size[1], step_w, device=x.device).long()  # w坐标轴
    grid_h, grid_w = torch.meshgrid(axis_h, axis_w)  # 生成网格
    output = x[:, :, grid_h, grid_w]

    return output


def _bilinear_interpolate(x: Tensor, size: Tuple[int, int] = None, scale_factor: float = None,
                          align_corners: bool = False) -> Tensor:
    """双线性插值(F.interpolate(mode="bilinear")) - 已重写简化

    :param x: shape = (N, C, Hin, Win)
    :param size: Tuple[Hout, Wout]
    :param scale_factor: size和scale_factor必须且只能提供其中的一个参数
    :param align_corners: 像素点当作像素方块来看待(与nearest不同)
        False: 输入和输出张量按其角像素的角点对齐。超过边界的值，插值使用边缘值填充
        True(保留角像素的值): 输入和输出张量按其角像素的中心点对齐
    :return: shape = (N, C, Hout, Wout)
    """

    in_size = x.shape[-2:]
    if scale_factor:
        size = int(in_size[0] * scale_factor), int(in_size[1] * scale_factor)  # out_size
    step_h, step_w = in_size[0] / size[0], in_size[1] / size[1]
    if align_corners:  # 角像素的中心点对齐(保留角像素的值)
        axis_h = torch.linspace(0, in_size[0] - 1, size[0], device=x.device)  # h坐标轴
        axis_w = torch.linspace(0, in_size[1] - 1, size[1], device=x.device)  # w坐标轴
    else:  # 角像素的角点对齐
        axis_h = torch.linspace(-0.5 + step_h / 2, - 0.5 + in_size[0] - step_h / 2, size[0], device=x.device)
        axis_w = torch.linspace(-0.5 + step_w / 2, - 0.5 + in_size[1] - step_w / 2, size[1], device=x.device)
    grid_h, grid_w = torch.meshgrid(axis_h, axis_w)  # 生成网格
    # if not align_corners:  # 超过边界的值，插值使用边缘值填充
    # 理论上align_corners == True时不需要截断，但是linespace会有误差，导致有时候过ceil()后索引时会越界，所以都加上
    grid_h.clamp_(0, in_size[0] - 1)
    grid_w.clamp_(0, in_size[1] - 1)
    # 以下6个张量都是2D的, shape(Hout * Wout, Hout * Wout)
    grid_h_f, grid_w_f = grid_h.long(), grid_w.long()  # floor
    grid_h_c, grid_w_c = grid_h.ceil().long(), grid_w.ceil().long()  # ceil
    offset_h, offset_w = grid_h - grid_h_f.float(), grid_w - grid_w_f.float()  # 与floor的偏离量
    # 左上角, 右上角, 左下角, 右下角
    output = (1 - offset_h) * (1 - offset_w) * x[:, :, grid_h_f, grid_w_f] + \
             (1 - offset_h) * offset_w * x[:, :, grid_h_f, grid_w_c] + \
             offset_h * (1 - offset_w) * x[:, :, grid_h_c, grid_w_f] + \
             offset_h * offset_w * x[:, :, grid_h_c, grid_w_c]
    return output


def _adaptive_avg_pool2d(x, output_size):
    """自适应的平均池化(F.adaptive_avg_pool2d())

    :param x: shape = (N, Hin, Win) or (N, Cin, Hin, Win)
    :return: shape = (N, Out[0], Out[1]) or (N, Cin, Out[0], Out[1])"""

    assert x.dim() in (3, 4)
    if isinstance(output_size, int):
        output_size = output_size, output_size

    # 切成output_size[0]个区间
    split_h = torch.linspace(0, x.shape[-2], output_size[0] + 1)
    split_w = torch.linspace(0, x.shape[-1], output_size[1] + 1)
    output = torch.empty((*x.shape[:-2], *output_size), dtype=x.dtype, device=x.device)

    for i in range(output.shape[-2]):
        for j in range(output.shape[-1]):
            pos_h = slice(split_h[i].int().item(), split_h[i + 1].ceil().int().item())
            pos_w = slice(split_w[j].int().item(), split_w[j + 1].ceil().int().item())

            output[..., i, j] = torch.mean(x[..., pos_h, pos_w], dim=(-2, -1))
    return output


def _adaptive_max_pool2d(x, output_size):
    """自适应的最大池化(F.adaptive_max_pool2d())
    notice: 不支持 return_indices.

    :param x: shape = (N, Hin, Win) or (N, Cin, Hin, Win)
    :return: shape = (N, Out[0], Out[1]) or (N, Cin, Out[0], Out[1])"""

    assert x.dim() in (3, 4)
    if isinstance(output_size, int):
        output_size = output_size, output_size

    # 切成output_size[0]个区间
    split_h = torch.linspace(0, x.shape[-2], output_size[0] + 1)
    split_w = torch.linspace(0, x.shape[-1], output_size[1] + 1)
    output = torch.empty((*x.shape[:-2], *output_size), dtype=x.dtype, device=x.device)

    for i in range(output.shape[-2]):
        for j in range(output.shape[-1]):
            pos_h = slice(split_h[i].int().item(), split_h[i + 1].ceil().int().item())
            pos_w = slice(split_w[j].int().item(), split_w[j + 1].ceil().int().item())
            output[..., i, j] = torch.max(torch.max(x[:, pos_h, pos_w], dim=-2)[0], dim=-1)[0]  # dim=(-2, -1)

    return output


def _rnn_cell(x0, h0, weight, bias=True):
    """h1/y1 = tanh(x0 @ W_ih^T + b_ih + h0 @ W_hh^T + b_hh)  (已测试)

    :param x0: shape[N, Cin].
    :param h0: shape[N, Ch]
    :param weight: List(weight_ih: shape[Ch, Cin], weight_hh: shape[Ch, Ch],
            bias_ih: shape[Ch], bias_hh: shape[Ch])
            len(4 or 2)
    :param bias: bool. 是否有bias
    :return: y1/h1: shape[N, Ch]
    """
    batch_size = x0.shape[0]
    if h0 is None:
        h0 = torch.zeros(batch_size, weight[0].shape[0])  # weight[0].shape[0]: Ch

    assert x0.shape[0] == h0.shape[0] and isinstance(bias, bool)  # N == N
    # weight  不经过验证

    y1 = torch.tanh(x0 @ weight[0].t() + (weight[2] if bias is not None else 0) +
                    h0 @ weight[1].t() + (weight[3] if bias is not None else 0))
    return y1


def _lstm_cell(x0, h0, c0, weight, bias=True):
    """(已测试)

    :param x0: shape[N, Cin].
    :param h0: shape[N, Ch]
    :param c0: shape[N, Ch]
    :param weight: List(weight_ih: shape[Ch*4, Cin], weight_hh: shape[Ch*4, Ch],
            bias_ih: shape[Ch*4], bias_hh: shape[Ch*4]). (i, f, g, o)
            len(4 or 2)
    :param bias: bool. 是否有bias
    :return: tuple(y1/h1: shape[N, Ch], c1: Tensor[N, Ch])
    """
    # i = σ(x0 @ Wii^T + bii + h0 @ Whi^T + bhi)
    # f = σ(x0 @ Wif^T + bif + h0 @ Whf^T + bhf)
    # g = tanh(x0 @ Wig^T + big + h0 @ Whg^T + bhg)
    # o = σ(x0 @ Wio^T + bio + h0 @ Who^T + bho)
    # c1 = f * c0 + i * g   # Hadamard乘积
    # h1 = o * tanh(c1)
    batch_size = x0.shape[0]
    c_hide = weight[0].shape[0] // 4  # Ch
    if h0 is None:
        h0 = torch.zeros(batch_size, c_hide)  # weight[0].shape[0]: Ch
    if c0 is None:
        c0 = torch.zeros(batch_size, c_hide)
    assert x0.shape[0] == h0.shape[0] == c0.shape[0] and isinstance(bias, bool)  # N == N == N
    # weight  不经过验证

    i = torch.sigmoid(x0 @ weight[0][0:c_hide].t() + (weight[2][0:c_hide] if bias is not None else 0) +
                      h0 @ weight[1][0:c_hide].t() + (weight[3][0:c_hide] if bias is not None else 0))
    f = torch.sigmoid(
        x0 @ weight[0][c_hide:c_hide * 2].t() + (weight[2][c_hide:c_hide * 2] if bias is not None else 0) +
        h0 @ weight[1][c_hide:c_hide * 2].t() + (weight[3][c_hide:c_hide * 2] if bias is not None else 0))
    g = torch.tanh(
        x0 @ weight[0][c_hide * 2:c_hide * 3].t() + (weight[2][c_hide * 2:c_hide * 3] if bias is not None else 0) +
        h0 @ weight[1][c_hide * 2:c_hide * 3].t() + (weight[3][c_hide * 2:c_hide * 3] if bias is not None else 0))
    o = torch.sigmoid(
        x0 @ weight[0][c_hide * 3:c_hide * 4].t() + (weight[2][c_hide * 3:c_hide * 4] if bias is not None else 0) +
        h0 @ weight[1][c_hide * 3:c_hide * 4].t() + (weight[3][c_hide * 3:c_hide * 4] if bias is not None else 0))
    c1 = f * c0 + i * g
    h1 = o * torch.tanh(c1)
    return h1, c1


def _gru_cell(x0, h0, weight, bias=True):
    """(已测试)

    :param x0: shape[N, Cin].
    :param h0: shape[N, Ch]
    :param weight: List(weight_ih: shape[Ch*3, Cin], weight_hh: shape[Ch*3, Ch],
            bias_ih: shape[Ch*3], bias_hh: shape[Ch*3]). (r, z, n)
            len(4 or 2)
    :param bias: bool. 是否有bias
    :return: y1/h1: shape[N, Ch]
    """

    batch_size = x0.shape[0]
    c_hide = weight[0].shape[0] // 3  # Ch
    if h0 is None:
        h0 = torch.zeros(batch_size, c_hide)  # weight[0].shape[0]: Ch

    assert x0.shape[0] == h0.shape[0] and isinstance(bias, bool)  # N == N == N
    # weight  不经过验证

    # r = σ(x0 @ Wir^T + bir + h0 @ Whr^T + bhr)  
    # z = σ(x0 @ Wiz^T + biz + h0 @ Whz^T + bhz)  
    # n = tanh(x0 @ Win^T + bin + r*(h @ Whn^T + bhn))  
    # h1/y1 = (1 − z) * n + z * h0
    r = torch.sigmoid(x0 @ weight[0][0:c_hide].t() + (weight[2][0:c_hide] if bias is not None else 0) +
                      h0 @ weight[1][0:c_hide].t() + (weight[3][0:c_hide] if bias is not None else 0))
    z = torch.sigmoid(
        x0 @ weight[0][c_hide:c_hide * 2].t() + (weight[2][c_hide:c_hide * 2] if bias is not None else 0) +
        h0 @ weight[1][c_hide:c_hide * 2].t() + (weight[3][c_hide:c_hide * 2] if bias is not None else 0))
    n = torch.tanh(
        x0 @ weight[0][c_hide * 2:c_hide * 3].t() + (weight[2][c_hide * 2:c_hide * 3] if bias is not None else 0) +
        r * (h0 @ weight[1][c_hide * 2:c_hide * 3].t() + (weight[3][c_hide * 2:c_hide * 3] if bias is not None else 0)))
    h1 = (1 - z) * n + z * h0
    return h1
