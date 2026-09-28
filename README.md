# 雨量空间插值与留站验证工具

纯 Python 3.12 标准库实现的命令行工具：根据本地雨量站的逐日观测，用距离平方倒数加权（IDW）估计目标点降雨，并对有实测值的站点执行留一站（leave-one-station-out）验证。

## 运行方式

```bash
python -m rainfall_interp <配置JSON> <观测CSV> <输出目录>
```

例如：

```bash
python -m rainfall_interp examples/config.json examples/observations.csv out
```

输出目录不存在时会自动创建；输入校验全部通过前不会生成或覆盖任何报告文件。

## 配置文件（JSON）

- `stations`：站点列表（非空），每项含 `id`（非空字符串）、`x`、`y`（有限数字）。站号必须唯一。
- `targets`：目标点列表（非空），结构与站点相同。目标编号必须唯一。
- `dates`：日期列表（非空），格式为 `YYYY-MM-DD`，不得重复。
- `radius`：搜索半径，非负有限数字；与坐标使用同一长度单位。
- `max_neighbors`：参与加权的邻居上限，正整数。

雨量单位由数据自行保证一致（例如均为 mm）。

## 观测文件（CSV）

必须包含列 `date,station_id,rainfall`：

- `date`：`YYYY-MM-DD`，必须出现在配置的日期列表中。
- `station_id`：必须是配置中的已知站号；同一日期同一站号不得重复。
- `rainfall`：非负有限数字。**空白表示缺测**，缺测记录不参与当天插值；`0` 是有效的零雨量。
- 某天某站完全没有记录同样视为缺测；不会跨日期填补。每个配置日期都会被处理（无有效观测时目标点标记为无覆盖）。

## 计算规则

对每个（日期、目标点）：

1. 只使用同一天的有效观测，计算各站到目标点的欧氏距离，保留距离不大于 `radius` 的站。
2. 若存在距离为 0 的站（同坐标），取这些站雨量的算术平均，**不受** `max_neighbors` 限制。
3. 否则按“距离升序、站号字典序”选取不超过 `max_neighbors` 个邻站，权重为 `1 / distance**2`，预测值为雨量加权和除以权重和。
4. 没有任何邻站时覆盖状态为无覆盖，预测值留空。

留一站验证：对每个有实测值的（日期、站点），先排除该站本身，再按完全相同的规则重新选站并预测（同坐标的其他站仍可参与）。误差定义为 `预测值 - 实测值`；无覆盖的验证项不参与误差指标统计。

## 输出文件

- `target_estimates.csv`：列 `date,target_id,prediction,covered,station_ids`，`station_ids` 为分号分隔的参与站号（按选择顺序）。
- `leave_one_out_validation.csv`：列 `date,station_id,observed,prediction,covered,error,station_ids`；缺失数值留空。
- `summary.json`：`daily`（逐日）与 `overall`（全体）分别给出：
  - `total`：验证记录总数（该日/全体有实测值的站点数）
  - `covered`：有预测值的验证数
  - `mean_error`：平均误差
  - `mean_absolute_error`：平均绝对误差
  - `root_mean_squared_error`：均方根误差

  指标仅按有覆盖的验证记录计算；没有有效记录时三个指标为 `null`。

所有 CSV 按日期、编号排序。

## 错误处理

非法输入（空/重复编号、非法坐标或日期、负雨量、未知站号、配置外日期、重复站点日期记录等）会输出带定位信息（如 `dates[0]`、`observations.csv row 3`）的错误信息并以非零状态码退出。

## 测试

```bash
python -m unittest discover -s tests -v
```
