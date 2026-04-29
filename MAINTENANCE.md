# Maintenance Guide for Spider OCR

This guide provides instructions for managing the Spider OCR environment, cleaning caches, and uninstalling the application.

## 🧹 Cleaning Cache and History

### Clear History (Database)
You can clear all extracted text history directly from the application's **History** page by clicking the "Clear All" (trash icon) in the header.

### Clear Build Cache
If you encounter build errors, remove the `builddir` and recreate it:
```bash
rm -rf builddir
./install.sh
```

### Clear Python Cache
Remove all `__pycache__` directories:
```bash
find . -name "__pycache__" -type d -exec rm -rf {} +
```

### Reset Application Settings
To reset window sizes and other GSettings:
```bash
gsettings reset-recursively org.domain.Spider
```

## 🚀 Reinstalling

To perform a clean reinstallation:
```bash
# 1. Clean up
rm -rf builddir .venv

# 2. Run install script
./install.sh

# 3. Launch
./builddir/org.domain.Spider
```

## 🗑️ Uninstallation

1. **Remove Build Artifacts**:
   ```bash
   rm -rf builddir .venv
   ```

2. **Remove Local Data** (History and Database):
   ```bash
   rm -rf ~/.local/share/spider
   ```

3. **Remove Source Code**:
   ```bash
   cd ..
   rm -rf spider
   ```
