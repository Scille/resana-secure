# Greatly inspired by Deluge NSIS installer
# https://github.com/deluge-torrent/deluge/blob/develop/packaging/win32/Win32%20README.txt

!addplugindir nsis_plugins
!addincludedir nsis_plugins
!include "WordFunc.nsh"

# Script version; displayed when running the installer
!define INSTALLER_SCRIPT_VERSION "1.0"

# Program information
!define PROGRAM_NAME "Resana Secure"
!define PROGRAM_WEB_SITE "https://resana.numerique.gouv.fr"
!define APPGUID "918CE5EB-F66D-45EB-9A0A-F013B480A5BC"

# Icon overlays GUIDS
!define CHECK_ICON_GUID "{5449BC90-310B-40A8-9ABF-C5CFCEC7F431}"
!define REFRESH_ICON_GUID "{41E71DD9-368D-46B2-BB9D-4359599BBBC4}"
# Icon overlays register entry
!define SHELL_ICON_OVERLAY_CHECK_ICON "SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\ShellIconOverlayIdentifiers\ResanaCheckIconHandler"
!define SHELL_ICON_OVERLAY_REFRESH_ICON "SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\ShellIconOverlayIdentifiers\ResanaRefreshIconHandler"

# Detect version from file
!define BUILD_DIR "build"
!searchparse /file ${BUILD_DIR}/manifest.ini `target = "` PROGRAM_FREEZE_BUILD_DIR `"`
!ifndef PROGRAM_FREEZE_BUILD_DIR
   !error "Cannot find freeze build directory"
!endif
!searchparse /file ${BUILD_DIR}/manifest.ini `program_version = "` PROGRAM_VERSION `"`
!ifndef PROGRAM_VERSION
   !error "Program Version Undefined"
!endif
!searchparse /file ${BUILD_DIR}/manifest.ini `platform = "` PROGRAM_PLATFORM `"`
!ifndef PROGRAM_PLATFORM
   !error "Program Platform Undefined"
!endif
!searchparse /file ${BUILD_DIR}/manifest.ini `winfsp_installer_path = "` WINFSP_INSTALLER_PATH `"`
!ifndef WINFSP_INSTALLER_PATH
   !error "WinFSP installer path Undefined"
!endif
!searchparse /file ${BUILD_DIR}/manifest.ini `winfsp_installer_name = "` WINFSP_INSTALLER_NAME `"`
!ifndef WINFSP_INSTALLER_NAME
   !error "WinFSP installer name Undefined"
!endif

# Python files generated
!define LICENSE_FILEPATH "${PROGRAM_FREEZE_BUILD_DIR}\LICENSE.txt"
!define INSTALLER_FILENAME "resana_secure-${PROGRAM_VERSION}-${PROGRAM_PLATFORM}-setup.exe"

# Set default compressor
SetCompressor /FINAL /SOLID lzma
SetCompressorDictSize 64

# --- Interface settings ---
# Modern User Interface 2
!include MUI2.nsh
# Installer
!define MUI_ICON "icon.ico"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_RIGHT
!define MUI_HEADERIMAGE_BITMAP "installer-top.bmp"
!define MUI_WELCOMEFINISHPAGE_BITMAP "installer-side.bmp"
!define MUI_COMPONENTSPAGE_SMALLDESC
!define MUI_ABORTWARNING
# Start Menu Folder Page Configuration
!define MUI_STARTMENUPAGE_DEFAULTFOLDER "${PROGRAM_NAME}"
!define MUI_STARTMENUPAGE_REGISTRY_ROOT "HKCR"
!define MUI_STARTMENUPAGE_REGISTRY_KEY "Software\${PROGRAM_NAME}"
!define MUI_STARTMENUPAGE_REGISTRY_VALUENAME "Start Menu Folder"
# Uninstaller
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"
!define MUI_HEADERIMAGE_UNBITMAP "installer-top.bmp"
!define MUI_WELCOMEFINISHPAGE_UNBITMAP "installer-side.bmp"
!define MUI_UNFINISHPAGE_NOAUTOCLOSE
# Add shortcut
!define MUI_FINISHPAGE_SHOWREADME ""
!define MUI_FINISHPAGE_SHOWREADME_TEXT "Create Desktop Shortcut"
!define MUI_FINISHPAGE_SHOWREADME_FUNCTION CreateDesktopShortcut
# !define MUI_FINISHPAGE_SHOWREADME_NOTCHECKED
# Run program after install, using explorer.exe to un-elevate priviledges
# More information: https://stackoverflow.com/a/15041823/2846140
!define MUI_FINISHPAGE_RUN "$WINDIR\explorer.exe"
!define MUI_FINISHPAGE_RUN_PARAMETERS "$INSTDIR\resana_secure.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Run Resana Secure"
# !define MUI_FINISHPAGE_RUN_NOTCHECKED

# --- Start of Modern User Interface ---
Var StartMenuFolder

# Welcome, License
!insertmacro MUI_PAGE_WELCOME
# No license for the moment
# !insertmacro MUI_PAGE_LICENSE ${LICENSE_FILEPATH}

# Skipping the components page
# !insertmacro MUI_PAGE_COMPONENTS

# Let the user select the installation directory
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_STARTMENU Application $StartMenuFolder

# Run installation
!insertmacro MUI_PAGE_INSTFILES
# Popup Message if VC Redist missing
# Page Custom VCRedistMessage
# Display 'finished' page
!insertmacro MUI_PAGE_FINISH
# Uninstaller pages
!insertmacro MUI_UNPAGE_INSTFILES
# Language files
!insertmacro MUI_LANGUAGE "English"


# --- Functions ---

; Taken from https://nsis.sourceforge.io/Get_parent_directory
; (NSIS project, Copyright (C) 1999-2021 Contributors, zlib/libpng license)
; GetParent
; input, top of stack  (e.g. C:\Program Files\Foo)
; output, top of stack (replaces, with e.g. C:\Program Files)
; modifies no other variables.
;
; Usage:
;   Push "C:\Program Files\Directory\Whatever"
;   Call GetParent
;   Pop $R0
;   ; at this point $R0 will equal "C:\Program Files\Directory"
Function GetParent

  Exch $R0
  Push $R1
  Push $R2
  Push $R3

  StrCpy $R1 0
  StrLen $R2 $R0

  loop:
    IntOp $R1 $R1 + 1
    IntCmp $R1 $R2 get 0 get
    StrCpy $R3 $R0 1 -$R1
    StrCmp $R3 "\" get
  Goto loop

  get:
    StrCpy $R0 $R0 -$R1

    Pop $R3
    Pop $R2
    Pop $R1
    Exch $R0

FunctionEnd

!macro checkProgramAlreadyRunning un message
Function ${un}checkProgramAlreadyRunning
    check:
        System::Call 'kernel32::OpenMutex(i 0x100000, b 0, t "resana-secure") i .R0'
        IntCmp $R0 0 notRunning
            System::Call 'kernel32::CloseHandle(i $R0)'
            MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION \
                "Resana Secure is running, please close it first.$\n$\n \
                Click `OK` to retry or `Cancel` to cancel this ${message}." \
                /SD IDCANCEL IDOK check
            Abort
    notRunning:
FunctionEnd
!macroend
!insertmacro checkProgramAlreadyRunning "" "upgrade"
!insertmacro checkProgramAlreadyRunning "un." "removal"

# Check for running program instance.
Function .onInit
    Call checkProgramAlreadyRunning

    SetRegView 64
    ReadRegStr $R0 HKLM \
    "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PROGRAM_NAME}" \
    "UninstallString"
    StrCmp $R0 "" done

    MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION \
    "${PROGRAM_NAME} is already installed. $\n$\nClick `OK` to remove the \
    previous version or `Cancel` to cancel this upgrade." \
    /SD IDOK IDOK uninst
    Abort

    ;Run the uninstaller sequentially and silently
    ;https://nsis.sourceforge.io/Docs/Chapter3.html#installerusageuninstaller
    uninst:
      ; Retrieve the previous version's install directory and store it into $R1.
      ; We cannot use ${INSTDIR} instead, given the previous version might
      ; have been installed in a custom directory.
      Push "$R0"
      Call GetParent
      Pop $R1
      ; ClearErrors
      ; If run without `_?=R1`, the uninstaller executable (i.e. `$R0`) will
      ; copy itself in a temporary directory, run this copy and exit right away.
      ; This is needed otherwise the installer won't be able to remove itself,
      ; however it also means `ExecWait` doesn't work here (the actuall uninstall
      ; process is still running when ExecWait returns).
      ; So we provide the ugly `_?=$R1` which, on top of being absolutly
      ; unreadable, does two things:
      ; - it force the directory to work on for the uninstaller (but we pass the
      ;   same previous version install directory as argument, so we change nothing here)
      ; - it tells the uninstaller not to do the "temp copy, exec and return"
      ;   trick and instead leave the uninstaller untouched.
      ; At this point, I'm very much puzzled as why writting NSIS installer
      ; feels like reverse engineering a taiwanese NES clone...
      ExecWait '"$R0" /S _?=$R1'

    done:

FunctionEnd

Function un.onUninstSuccess
    HideWindow
    MessageBox MB_ICONINFORMATION|MB_OK "$(^Name) was successfully removed from your computer." /SD IDOK
FunctionEnd

Function un.onInit
    Call un.checkProgramAlreadyRunning
    SetRegView 64
    MessageBox MB_ICONQUESTION|MB_YESNO|MB_DEFBUTTON2 "Do you want to completely remove $(^Name)?" /SD IDYES IDYES +2
    Abort
FunctionEnd

Function CreateDesktopShortcut
    CreateShortCut "$DESKTOP\Resana Secure.lnk" "$INSTDIR\resana_secure.exe"
FunctionEnd

# # Test if Visual Studio Redistributables 2008 SP1 installed and returns -1 if none installed
# Function CheckVCRedist2008
#     Push $R0
#     ClearErrors
#     ReadRegDword $R0 HKLM "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{FF66E9F6-83E7-3A3E-AF14-8DE9A809A6A4}" "Version"
#     IfErrors 0 +2
#         StrCpy $R0 "-1"
#
#     Push $R1
#     ClearErrors
#     ReadRegDword $R1 HKLM "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{9BE518E6-ECC6-35A9-88E4-87755C07200F}" "Version"
#     IfErrors 0 VSRedistInstalled
#         StrCpy $R1 "-1"
#
#     StrCmp $R0 "-1" +3 0
#         Exch $R0
#         Goto VSRedistInstalled
#     StrCmp $R1 "-1" +3 0
#         Exch $R1
#         Goto VSRedistInstalled
#     # else
#         Push "-1"
#     VSRedistInstalled:
# FunctionEnd
#
# Function VCRedistMessage
#     Call CheckVCRedist2008
#     Pop $R0
#     StrCmp $R0 "-1" 0 end
#     MessageBox MB_YESNO|MB_ICONEXCLAMATION "Resana Secure requires an MSVC package to run \
#     but the recommended package does not appear to be installed:$\r$\n$\r$\n\
#     Microsoft Visual C++ 2008 SP1 Redistributable Package (x86)$\r$\n$\r$\n\
#     Would you like to download it now?" /SD IDNO IDYES clickyes
#     Goto end
#     clickyes:
#         ExecShell open "https://www.microsoft.com/en-us/download/details.aspx?id=26368"
#     end:
# FunctionEnd

!macro DeleteOrMoveFile dir temp name
    # This routine ensures that we are not leaving an old `${dir}\${name}` file in place
    # Case 1: the DLL file is not used:
    #  - it's properly deleted
    # Case 2: the DLL file is used, and is in the same drive as `${temp}`:
    #  - the file is moved to `${temp}`
    # Case 3: the DLL file is used, and is not in the same drive as `${temp}`:
    #  - the file is renamed in-place as `${temp}.old`
    Delete "${dir}\${name}"
    Delete "${dir}\${name}.old"
    Delete "${temp}\${name}.old"
    Rename "${dir}\${name}" "${dir}\${name}.old"
    Rename "${dir}\${name}.old" "${temp}\${name}.old"
    Delete "${temp}\${name}.old"
!macroend

!macro MoveParsecShellExtension
    # When upgrading or uninstalling, shell extensions may be loaded by `explorer.exe`
    # thus windows will prevent us to delete or modify the dll extensions. The trick
    # here is to move the loaded dll somewhere else (like in a temp folder) and then resume
    # the upgrade/uninstall process as usual.
    RmDir /r "$TEMP\parsec_tmp"
    CreateDirectory "$TEMP\parsec_tmp"
    !insertmacro DeleteOrMoveFile "$INSTDIR" "$TEMP\parsec_tmp" "check-icon-handler.dll"
    !insertmacro DeleteOrMoveFile "$INSTDIR" "$TEMP\parsec_tmp" "refresh-icon-handler.dll"
    !insertmacro DeleteOrMoveFile "$INSTDIR" "$TEMP\parsec_tmp" "vcruntime140.dll"
    !insertmacro DeleteOrMoveFile "$INSTDIR" "$TEMP\parsec_tmp" "vcruntime140_1.dll"
!macroend

# --- Installation sections ---
!define PROGRAM_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PROGRAM_NAME}"
!define PROGRAM_UNINST_ROOT_KEY "HKLM"
!define PROGRAM_UNINST_FILENAME "$INSTDIR\uninstall.exe"

BrandingText "${PROGRAM_NAME} Windows Installer v${INSTALLER_SCRIPT_VERSION}"
Name "${PROGRAM_NAME} ${PROGRAM_VERSION}"
OutFile "${BUILD_DIR}\${INSTALLER_FILENAME}"
InstallDir "$PROGRAMFILES\Resana Secure"

# No need for such details
ShowInstDetails hide
ShowUnInstDetails hide

# Install main application
Section "Resana Secure Cloud Sharing" Section1
    !insertmacro MoveParsecShellExtension
    SectionIn RO
    !include "${BUILD_DIR}\install_files.nsh"

    SetOverwrite ifnewer
    SetOutPath "$INSTDIR"
    WriteIniStr "$INSTDIR\homepage.url" "InternetShortcut" "URL" "${PROGRAM_WEB_SITE}"

    !insertmacro MUI_STARTMENU_WRITE_BEGIN Application
        SetShellVarContext all
        CreateDirectory "$SMPROGRAMS\$StartMenuFolder"
        CreateShortCut "$SMPROGRAMS\$StartMenuFolder\Resana Secure.lnk" "$INSTDIR\resana_secure.exe"
        CreateShortCut "$SMPROGRAMS\$StartMenuFolder\Website.lnk" "$INSTDIR\homepage.url"
        CreateShortCut "$SMPROGRAMS\$StartMenuFolder\Uninstall Resana Secure.lnk" ${PROGRAM_UNINST_FILENAME}
        SetShellVarContext current
    !insertmacro MUI_STARTMENU_WRITE_END

    # Call regsvr32
    ExecWait '$SYSDIR\regsvr32.exe /s /n /i:user "$INSTDIR\check-icon-handler.dll"'
    ExecWait '$SYSDIR\regsvr32.exe /s /n /i:user "$INSTDIR\refresh-icon-handler.dll"'

    # Write Icons overlays to register
    WriteRegStr ${PROGRAM_UNINST_ROOT_KEY} "${SHELL_ICON_OVERLAY_CHECK_ICON}" "" "${CHECK_ICON_GUID}"
    WriteRegStr ${PROGRAM_UNINST_ROOT_KEY} "${SHELL_ICON_OVERLAY_REFRESH_ICON}" "" "${REFRESH_ICON_GUID}"
SectionEnd

!macro InstallWinFSP
    SetOutPath "$TEMP"
    File ${WINFSP_INSTALLER_PATH}
    ; Use /qn to for silent installation
    ; Use a very high installation level to make sure it runs till the end
    ExecWait "msiexec /i ${WINFSP_INSTALLER_NAME} /qn INSTALLLEVEL=1000"
    Delete ${WINFSP_INSTALLER_NAME}
!macroend

# Install winfsp if necessary
Section "WinFSP" Section2
    ClearErrors
    ReadRegStr $0 HKCR "Installer\Dependencies\WinFsp" "Version"
    ${If} ${Errors}
      # WinFSP is not installed
      !insertmacro InstallWinFSP
    ${Else}
        ${VersionCompare} $0 "1.3.0" $R0
        ${VersionCompare} $0 "2.0.0" $R1
        ${If} $R0 == 2
            ${OrIf} $R1 == 1
                ${OrIf} $R1 == 0
                  # Incorrect WinSFP version (<1.4.0 or >=2.0.0)
                  !insertmacro InstallWinFSP
        ${EndIf}
    ${EndIf}
SectionEnd

# Hidden: Remove obsolete entries
Section "-Remove obsolete entries" Section4
    # Remove obsolete parsec registry configuration
    DeleteRegKey HKCU "Software\Classes\CLSID\{${APPGUID}}"
    DeleteRegKey HKCU "Software\Classes\Wow6432Node\CLSID\{${APPGUID}}"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Explorer\Desktop\NameSpace\{${APPGUID}}"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Explorer\HideDesktopIcons\NewStartPanel\{${APPGUID}}"
    ClearErrors
SectionEnd

# The components screen is skipped - this is no longer necessary
# LangString DESC_Section1 ${LANG_ENGLISH} "Install Resana Secure."
# LangString DESC_Section2 ${LANG_ENGLISH} "Install WinFSP."
# LangString DESC_Section3 ${LANG_ENGLISH} "Let Resana Secure handle parsec:// URI links from the web-browser."
# LangString DESC_Section4 ${LANG_ENGLISH} "Remove obsolete entries from outdated parsec installation."
# !insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
#     !insertmacro MUI_DESCRIPTION_TEXT ${Section1} $(DESC_Section1)
#     !insertmacro MUI_DESCRIPTION_TEXT ${Section2} $(DESC_Section2)
#     !insertmacro MUI_DESCRIPTION_TEXT ${Section3} $(DESC_Section3)
#     !insertmacro MUI_DESCRIPTION_TEXT ${Section4} $(DESC_Section4)
# !insertmacro MUI_FUNCTION_DESCRIPTION_END

# Create uninstaller.
Section -Uninstaller
    WriteUninstaller ${PROGRAM_UNINST_FILENAME}
    WriteRegStr ${PROGRAM_UNINST_ROOT_KEY} "${PROGRAM_UNINST_KEY}" "DisplayName" "$(^Name)"
    WriteRegStr ${PROGRAM_UNINST_ROOT_KEY} "${PROGRAM_UNINST_KEY}" "UninstallString" ${PROGRAM_UNINST_FILENAME}
SectionEnd

# --- Uninstallation section ---
Section Uninstall
    !insertmacro MoveParsecShellExtension

    DeleteRegKey ${PROGRAM_UNINST_ROOT_KEY} "${SHELL_ICON_OVERLAY_CHECK_ICON}"
    DeleteRegKey ${PROGRAM_UNINST_ROOT_KEY} "${SHELL_ICON_OVERLAY_REFRESH_ICON}"

    ExecWait '$SYSDIR\regsvr32.exe /s /u /n /i:user "$INSTDIR\check-icon-handler.dll"'
    ExecWait '$SYSDIR\regsvr32.exe /s /u /n /i:user "$INSTDIR\refresh-icon-handler.dll"'

    # Delete program files.
    Delete "$INSTDIR\homepage.url"
    Delete ${PROGRAM_UNINST_FILENAME}
    !include "${BUILD_DIR}\uninstall_files.nsh"
    RmDir "$INSTDIR"

    # Delete Start Menu items.
    !insertmacro MUI_STARTMENU_GETFOLDER Application $StartMenuFolder
        SetShellVarContext all
        Delete "$SMPROGRAMS\$StartMenuFolder\Resana Secure.lnk"
        Delete "$SMPROGRAMS\$StartMenuFolder\Uninstall Resana Secure.lnk"
        Delete "$SMPROGRAMS\$StartMenuFolder\Resana Secure Website.lnk"
        RmDir "$SMPROGRAMS\$StartMenuFolder"
        DeleteRegKey /ifempty HKCR "Software\Resana Secure"
        SetShellVarContext current
    Delete "$DESKTOP\Resana Secure.lnk"

    # Delete registry keys.
    DeleteRegKey ${PROGRAM_UNINST_ROOT_KEY} "${PROGRAM_UNINST_KEY}"
    # This key is only used by Resana Secure, so we should always delete it
    DeleteRegKey HKCR "Resana Secure"

    # Explorer shortcut keys potentially set by the application's settings
    DeleteRegKey HKCU "Software\Classes\CLSID\{${APPGUID}}"
    DeleteRegKey HKCU "Software\Classes\Wow6432Node\CLSID\{${APPGUID}"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Explorer\Desktop\NameSpace\{${APPGUID}"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Explorer\HideDesktopIcons\NewStartPanel\{${APPGUID}"
SectionEnd

# Add version info to installer properties.
VIProductVersion "${INSTALLER_SCRIPT_VERSION}.0.0"
VIAddVersionKey ProductName "${PROGRAM_NAME}"
VIAddVersionKey Comments "Resana Secure - secure sharing plugin for Resana"
VIAddVersionKey CompanyName "Scille SAS"
VIAddVersionKey LegalCopyright "Scille SAS"
VIAddVersionKey FileDescription "${PROGRAM_NAME} Application Installer"
VIAddVersionKey FileVersion "${INSTALLER_SCRIPT_VERSION}.0.0"
VIAddVersionKey ProductVersion "${PROGRAM_VERSION}.0"
VIAddVersionKey OriginalFilename ${INSTALLER_FILENAME}

ManifestDPIAware true
