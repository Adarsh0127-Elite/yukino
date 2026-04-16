### A Simple Script to upload Files to your bot by using https://gofile.io via Terminal (CLI)

#### Usage Instructions for Linux Environment:

- To make the script globally available, run the following commands in your terminal:
```bash
   sudo wget https://raw.githubusercontent.com/Adarsh0127-Elite/yukino/main/upload.sh -O "/usr/local/bin/upload.sh"
   sudo chmod +x /usr/local/bin/upload.sh
```

- To uninstall gofile, you can run:
```bash
   sudo rm "/usr/local/bin/upload.sh"
```

#### How to Upload Files:

1. Run the script inside the home directory of your rom and the script will automatically choose the devicecode name along with the build and all:
```bash
   upload.sh
```

## Non-Root installation (bash)
```bash
wget -q https://raw.githubusercontent.com/Adarsh0127-Elite/yukino/main/upload.sh -O ~/upload && chmod +x ~/upload.sh
echo 'alias upload="~/upload"' >> ~/.bashrc && source ~/.bashrc
```
Then run this in the home directory of the rom:
```bash
upload.sh
```

## Based on
- Original script: https://github.com/Sushrut1101/GoFile-Upload
- 
## Credits:
- [Adarsh0127-Elite](https://github.com/Adarsh0127-Elite)
- https://gofile.io - For the amazing website to upload unlimited files, for free
