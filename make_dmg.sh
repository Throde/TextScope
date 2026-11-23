#!/bin/bash
# 要运行此脚本，在终端中输入： ./make_dmg.sh
set -e # 开启“遇到任何非零返回码就立刻退出”，避免中间某步失败却继续往下跑。

# 版本号，用来拼接输出 DMG 文件名。按你的版本改，不影响 DMG 内容本身，只是命名好看。
VERSION="V1.1.1"

APP_NAME="TextScope_${VERSION}.app"
APP_DIR="dist"

# DMG 挂载后的“卷名”（用户双击 DMG 后看到的磁盘名称）。通常取 App 名的简短版本。可随意定制，影响的是挂载盘的显示名。
VOL_NAME="TextScope"

# 暂存目录：把要打包进 DMG 的东西先放这里。一般不用改。
STAGING="$APP_DIR/dmg_staging"

# 生成的 DMG 文件路径和文件名。会变成类似 dist/TextScope_V1.0.0_mac.dmg。想把 DMG 放到别的目录，改这里。
DMG_PATH="$APP_DIR/${VOL_NAME}_${VERSION}_mac.dmg"

echo "🔧 开始制作 DMG..."

# 清理旧的暂存目录，避免残留影响。-rf 表示递归强制删除。注意：路径已用引号包住，避免空格问题。
rm -rf "$STAGING"
# 新建暂存目录。-p 表示父目录不存在时也一起建。
mkdir -p "$STAGING"

# 递归复制 .app 到暂存目录里：
cp -R "$APP_DIR/$APP_NAME" "$STAGING/"
# 递归复制其他要打包进 dmg 的外部资源目录：
# cp -R "$APP_DIR/TextScope_Resources" "$STAGING/TextScope_Resources"
# 创建一个指向系统 /Applications 的符号链接。用户打开 DMG 后会看到一个“Applications”图标，这样他们可以把 App 拖拽过去完成安装（是标准做法）。
ln -s /Applications "$STAGING/Applications"

# 用系统自带的 hdiutil 创建 DMG 的关键一步。
# -volname "$VOL_NAME"：设置挂载卷名（上面定义的）。
# -srcfolder "$STAGING"：把这个目录里的内容打进 DMG。
# -ov：允许覆盖已有的同名 DMG（overwrite）。
# -format UDZO：采用 压缩只读 格式（zlib 压缩）。体积和兼容性的折中方案。
hdiutil create -volname "$VOL_NAME" -srcfolder "$STAGING" -ov -format UDZO "$DMG_PATH"

# 清理暂存目录。DMG 已生成，这些中间文件可以删掉。
rm -rf "$STAGING"

echo "✅ 已生成 DMG：$DMG_PATH"
