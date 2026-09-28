# TinyNote v1.0.0

Windows 上的 Python 透明单行速记框。**Ctrl+Alt+A** 唤出或收起，中文选词确认后直接保存到 Markdown，遇到 **`。`** 自动换行。

## 启动

1. 安装 Python 3.10+，推荐稳定版 Python 3.12 或 3.13。
2. 首次使用双击 `setup.cmd` 安装依赖。
3. 双击 **`start.cmd`**，会直接出现一个 **320×34** 的透明小框。

程序也会驻留系统托盘。点击其他窗口后自动保存并收起，再按 **Ctrl+Alt+A** 唤出。

从早期试用版更新时，请先从托盘菜单退出旧版，再双击 `start.cmd`。新版重复启动会唤出已有实例。

启动脚本按顺序查找项目虚拟环境、`python`、`py -3`，使用具备 PySide6 的解释器运行；支持空格和中文路径。启动失败时窗口会保留提示，详细错误在 `.runtime/startup.log`。程序正文不会写入日志。

手动运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py --show
```

省略 `--show` 时默认只驻留托盘。`--data-dir "D:\我的笔记"` 可更换配置和笔记所在目录；`--quit` 可让同目录的新版实例保存并退出。

## 单行输入与光标

- 默认隐藏正文，输入框只占一行，不弹出预览框。
- **←**：光标向左移动一个字符，进入可见编辑模式，只显示当前行中**光标前最多 4 个字**及光标。继续按 ← 可回到已保存的上一行。
- 在可见编辑模式下输入、退格或删除，直接修改光标所在位置；后面的文字保留。可见范围随光标移动，不自动弹出其他窗口或计时消失。
- **→**：光标向右移动一个字符，同时恢复隐藏；之后输入仍发生在这个光标位置。
- **Ctrl+End**：回到整份笔记末尾。想继续追加时，先按 Ctrl+End，再按 → 隐藏。
- 单行显示只是一个编辑窗口，Markdown 文件仍可包含多行完整历史。
- 中文输入法组词时，方向键、Tab、Enter 优先交给输入法；未确认的拼音不会保存。

例如输入 `今天去公园散步` 后，按一次 ←，透明框显示 `去公园散|`。此时输入 `慢`，文件变为 `今天去公园散慢步`，框里显示 `公园散慢|`。再按 →，光标越过 `步` 并隐藏正文。

系统输入法候选窗由输入法控制，可能仍然可见。隐藏仅作用于界面，Markdown 文件本身是普通文本，没有加密。

## 保存与换行

每次中文选词确认同步保存，同一句持续追加，不会因一次选词就换行。默认收到新输入的 `。` 后保留句号并换行，英文句点、小数和网址不触发换行。在中间插入句号时，后面的文字移到下一行，光标仍停在插入处。

例如依次确认「今天」「开会」「。」「记得带电脑」，文件内容为：

```markdown
今天开会。
记得带电脑
```

普通键盘输入、粘贴、退格等在内容停止变化约 180 毫秒后保存。**Enter** 在光标处插入换行；切换文件、收起和退出只保存，不额外插入空行。

默认笔记目录为 `notes/`，初始文件为 `随手记.md`、`灵感.md`、`待办.md`。新建 `.md` 文件会加入切换列表。

保存采用同目录临时文件、刷新磁盘和原子替换。磁盘写入失败会保留输入并阻止切换、收起和正常退出。外部程序同时修改文件时，保留外部版本，把本程序中的完整编辑结果另存为 `恢复-时间戳.md`。没有本地修改时会读取外部更新。无法对任意第三方编辑器提供跨程序事务锁，不建议同时编辑同一个文件。

## 快捷键

| 快捷键 | 功能 |
| --- | --- |
| **Ctrl+Alt+A** | 全局唤出 / 收起 |
| **←** | 左移光标，显示光标前最多 4 字 |
| **→** | 右移光标，恢复隐藏 |
| Ctrl+End / Ctrl+Home | 移到整份笔记末尾 / 开头 |
| Enter | 在光标处换行并保存 |
| Backspace / Delete | 删除光标前 / 后的字符 |
| Ctrl+Z / Ctrl+Y | 撤销 / 重做 |
| Tab / Shift+Tab | 下一份 / 上一份 Markdown |
| Ctrl+1 … Ctrl+9 | 切换前 9 份笔记 |
| Ctrl+N | 新建笔记 |
| Ctrl+V | 在光标处粘贴 |
| Ctrl+O | 打开笔记目录 |
| Ctrl+Shift+O | 用默认程序打开当前 Markdown |
| Ctrl+K | 命令与扩展入口 |
| Ctrl+, | 设置换行模式和透明度 |
| F1 | 快捷键帮助 |
| F2 | 临时切换背景不透明度 |
| Esc | 保存并收起 |
| Ctrl+Q | 保存并退出 |

框左侧文件名可以点开文件菜单。顶部细边可拖动窗口。保存状态放在右侧小点的悬停提示里，失败时显示 `!`。

为避免误复制不可见内容，输入框内禁用 Ctrl+C / Ctrl+X，需要复制历史时可打开 Markdown 文件操作。

全局热键优先使用 Windows RegisterHotKey；被其他程序占用时，默认尝试兼容模式，仅接管所配置的组合键。退出后释放，不修改其他程序设置。兼容模式不保证能接管更高权限应用或其他拦截器的按键。

## 配置与扩展

首次启动自动生成 `config.json`。完整示例见 [`config.example.json`](config.example.json)。设置面板即时生效，手动编辑配置后需重启。

```json
{
  "global_hotkey": "Ctrl+Alt+A",
  "hotkey_fallback": true,
  "window_width": 320,
  "context_chars": 4,
  "opacity": 0.03,
  "notes_dir": "notes",
  "newline_mode": "punctuation",
  "autosave_ms": 180,
  "hide_on_blur": true,
  "plugins": []
}
```

`opacity` 是背景不透明度，`0` 表示不填充背景，边框仍可见。文字可见与否由左右方向键控制。`newline_mode` 支持 `punctuation`（中文句号）、`manual`（Enter）、`idle`（停顿）和 `ime`（每次选词）。快捷键在 `shortcuts` 中重映射，空字符串表示禁用。

在配置中加入 `"plugins": ["plugins.timestamp"]`，重启后可按 **Ctrl+T** 插入当前时间，也能从 Ctrl+K 菜单找到该命令。

```python
def setup(api):
    api.register_command(
        "insert_todo", "插入待办标记",
        lambda: api.insert_text("- [ ] "), "Ctrl+J"
    )
    api.on("saved", lambda path, text, committed: None)
    api.on("file_changed", lambda path: None)
```

`api.current_path` 是当前笔记路径。`saved` 的 `text` 是整份文档快照；`committed` 表示这次保存是否由显式换行触发。扩展拥有当前进程权限，请只加载可信的本地扩展，耗时操作自行放入工作线程。

## 验证与项目结构

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
# 可选：退出正在运行的程序后验证全局热键
.\.venv\Scripts\python.exe -X utf8 -m tests.smoke_native
```

测试覆盖光标原位编辑、跨行修改、四字上下文、Unicode、中文输入法事件、隐藏绘制、句号换行、文件切换、保存失败与冲突恢复，以及真正执行 `.cmd` 的启动、重复启动和退出流程。输入法事件测试使用 Qt 合成事件，实际系统候选窗由所用输入法决定。

- `launcher.py`：解释器启动、后台进程和错误反馈。
- `tinynote/editor.py`：透明单行绘制、真实光标和中文输入法。
- `tinynote/storage.py`：文档快照与 Markdown 原子保存。
- `tinynote/hotkey.py`：全局热键与冲突兼容。
- `tinynote/instance.py`：单实例唤出和正常退出。
- `tinynote/app.py`：窗口、快捷命令、托盘与设置。
- `tinynote/extensions.py`、`plugins/`：扩展接口和示例。

仓库不包含个人笔记、实际配置、日志或本地虚拟环境。
