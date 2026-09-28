# rainfall_interp — 雨量站空间插值与留站验证

仅使用 Python 3.12 标准库。根据本地雨量站的逐日降雨观测，用距离平方倒数
加权（IDW）插值估计目标点的逐日降雨，并执行留一站（leave-one-station-out）
验证，报告覆盖情况与预测误差。

## 运行

```bash
python -m rainfall_interp --config examples/config.json \
                         --observations examples/observations.csv \
                         --output-dir examples/output
```

参数：

- `-c/--config`：JSON 配置文件路径
- `-o/--observations`：观测 CSV 文件路径
- `-d/--output-dir`：报告输出目录（不存在时创建）

输入校验失败时不生成或覆盖任何报告，进程以退出码 `2` 结束，错误信息定位到
具体字段或行（如 `config: stations[2].x`、`observations: row 5.rainfall`）。

## 配置文件（JSON）

```json
{
  "stations": [
    {"id": "S1", "x": 0.0, "y": 0.0},
    {"id": "S2", "x": 10.0, "y": 0.0}
  ],
  "targets": [
    {"id": "T1", "x": 5.0, "y": 5.0}
  ],
  "dates": ["2024-06-01", "2024-06-02"],
  "radius": 15.0,
  "max_neighbors": 3
}
```

- `stations` / `targets`：非空列表，每项含非空且唯一的 `id`、有限数值 `x`/`y`
  （平面坐标，站号与目标编号各自唯一）。
- `dates`：非空的合法日历日期列表，格式 `YYYY-MM-DD`，不可重复。
- `radius`：非负有限搜索半径，与坐标使用同一长度单位（边界距离取等号，
  即距离 `<= radius` 的站点入选）。`0` 合法，表示仅同坐标站可用。
- `max_neighbors`：正整数，参与加权的邻站数量上限。

## 观测文件（CSV）

必须包含表头列 `date,station_id,rainfall`：

```csv
date,station_id,rainfall
2024-06-01,S1,2.0
2024-06-01,S2,
2024-06-02,S1,0.0
```

- 日期必须在配置 `dates` 内；站号必须在配置 `stations` 内，否则报错。
- 同一 (日期, 站号) 出现多条记录视为重复，报错。
- `rainfall` 必须是非负有限数值，单位需自行保持统一。
- **空白雨量或整条记录缺测**均表示缺测，不参与任何计算；`0` 是有效雨量。
- 只使用同一天的有效观测，**不跨日期填补**；每个配置日期都会被处理。

## 插值规则

对每个 (日期, 目标点)：

1. 选取当日有有效观测、且欧氏距离不大于 `radius` 的站点。
2. 若存在距离为 0（与目标同坐标）的站点：只取这些站，预测值为其雨量的
   算术平均，**不受 `max_neighbors` 限制**。
3. 否则将候选站按（距离升序, 站号字典序）排序，取前 `max_neighbors` 个，
   以距离平方倒数为权重：

   ```
   w_i = 1 / d_i^2
   预测 = Σ(w_i · r_i) / Σ w_i
   ```

4. 没有任何候选站时，覆盖状态记为无覆盖（`covered=no`），预测值留空。

## 留一站验证

对每个有实测值的 (日期, 站点)：先排除该站自身，再按上述完全相同的规则
重新选邻站并预测该站位置的雨量。同坐标的其他站可以正常参与（此时触发
同坐标算术平均）。无覆盖的验证项不参与误差统计。

- 误差定义：`error = prediction - actual`（预测减实测）。

## 输出文件

### `target_estimates.csv`

列：`date, id, prediction, covered, participant_ids`

- 每个配置日期 × 每个目标点一行，按日期、编号排序。
- `covered` 为 `yes`/`no`；无覆盖时 `prediction` 留空。
- `participant_ids` 为参与站点编号，按规则顺序以 `;` 连接，无覆盖时为空。

### `leave_one_out.csv`

列：`date, id, actual, prediction, error, covered, participant_ids`

- 每个有实测值的站-日期一行；`actual` 为实测值。
- 无覆盖时 `prediction`、`error` 留空。

### `summary.json`

```json
{
  "daily": {
    "2024-06-01": {
      "total": 4,
      "covered": 3,
      "mean_error": -0.4444,
      "mean_absolute_error": 3.1111,
      "root_mean_squared_error": 3.849
    }
  },
  "overall": {
    "total": 8,
    "covered": 7,
    "mean_error": null,
    "mean_absolute_error": null,
    "root_mean_squared_error": null
  }
}
```

- `total`：验证记录总数；`covered`：有预测的记录数。
- 指标仅按覆盖记录计算：平均误差（ME）、平均绝对误差（MAE）、
  均方根误差（RMSE，根号内除以覆盖记录数）。
- 某日或全体没有任何覆盖记录时，三项指标均为 `null`（计数仍给出）。

## 测试

```bash
python -m unittest discover -s tests
```
