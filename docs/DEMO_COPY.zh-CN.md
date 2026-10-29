# MotionMontage Demo 文案

本次公开预览只使用之前已验证的 **SMPL-H 人体网格**（SMPL 系列）。不使用骨架、胶囊体或程序小人代替人体；工程诊断样例不进入这份 Demo 总览。人体网格、世界 root 与原始时间保持不变，相机方案与显示配色单独配置。

| Demo | 中文说明 | 图片上的英文 Prompt |
|---|---|---|
| 单独 Motion | 人物行走，展示 SMPL 网格时序；隐藏相机。 | Motion: A person walks. |
| 单独 Camera：纯线框 | 沿用跟随轨迹，仅用线框表达相机方向。 | Camera: The camera follows a walking person with a fixed orientation. |
| 单独 Camera：实体相机 | 同一相机轨迹，增加机身、镜头、时间标签和方向箭头。 | Camera: The camera follows a walking person with a fixed orientation. |
| Motion + Camera | 同一个世界坐标中查看人物行走和相机跟随。 | Motion: A person walks. Camera: The camera follows the person with a fixed orientation. |
| 实际相机视角 | 直接展示输入相机看到的画面。 | Motion: A person walks. Camera: The camera follows the person with a fixed orientation. |
| 固定机位 | 人物继续行走，相机位置与朝向不变。 | Motion: A person walks. Camera: The camera stays at a fixed position and orientation. |
| 环绕并跟随 | 人体动作保持原样，相机沿一段弧线环绕并跟随。 | Motion: A person walks. Camera: The camera orbits and follows the person. |
| 透明 PNG | 保留真实 alpha，可用于论文排版；网页棋盘格不写入图片。 | 按对应模态使用上面的 Prompt。 |
| 单色 / 时序渐变 / 多色 | 配色只编码时间，不改变动作或相机。 | 按对应模态使用上面的 Prompt。 |
| 关键帧 | 灰色强调指定时刻，其他姿态按时间配色。 | 按对应模态使用上面的 Prompt。 |

所有静态 Demo 在图片顶部写英文 Prompt，在网页上提供中文说明和同一份英文 Prompt。已有完整视频保留原有真实输入说明，不冒称重新生成或升级了底层版本。

相机示意线框的纵深默认压缩至 55%，不改变相机真实焦距、朝向或相机视角画面。将 `--frustum-depth-ratio` 设为 `1` 可恢复符合标定比例的形状；两种 Camera 外观都支持这个选项。
