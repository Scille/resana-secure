#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <windows.h>
#include <stdio.h>
#include <tchar.h>
#include <wintrust.h>
#include <wincrypt.h>
#include <Softpub.h>

// Information structure of authenticode sign
typedef struct
{
    LPWSTR lpszProgramName;
    LPWSTR lpszPublisherLink;
    LPWSTR lpszMoreInfoLink;

    DWORD cbSerialSize;
    LPBYTE lpSerialNumber;
    LPTSTR lpszIssuerName;
    LPTSTR lpszSubjectName;
} SPROG_SIGNATUREINFO, *PSPROG_SIGNATUREINFO;

#define ENCODING (X509_ASN_ENCODING | PKCS_7_ASN_ENCODING)

LONG SD_VerifyEmbeddedSignature(LPCTSTR pszSourceFile);
BOOL SD_GetAuthenticodeInformation(LPCTSTR lpszFileName, PSPROG_SIGNATUREINFO pInfo);
VOID GetCertificateInfo(HCERTSTORE hStore, PCMSG_SIGNER_INFO pSignerInfo, PSPROG_SIGNATUREINFO pInfo);
VOID GetProgAndPublisherInfo(PCMSG_SIGNER_INFO pSignerInfo, PSPROG_SIGNATUREINFO pInfo);
LPWSTR AllocateAndCopyWideString(LPCWSTR inputString);

static LONG SD_VerifyEmbeddedSignature(LPCTSTR pszSourceFile)
{
    LONG lStatus;
    DWORD dwLastError;
    WCHAR wszFileName[MAX_PATH];
    WINTRUST_FILE_INFO FileData;
    BOOL DoSecondPass;
    unsigned int Count;

    // Initialize the WINTRUST_FILE_INFO structure.
#ifdef UNICODE
    lstrcpynW(wszFileName, pszSourceFile, MAX_PATH);
#else
    size_t RetSize;

    //mbstowcs( wszFileName, pszSourceFile, MAX_PATH);
    //Remplacé pour la certifié en:
    mbstowcs_s(&RetSize, wszFileName, MAX_PATH, pszSourceFile, _TRUNCATE);
#endif

    DoSecondPass = FALSE;
    Count = 0;

    do
    {
        memset(&FileData, 0, sizeof(FileData));
        FileData.cbStruct = sizeof(WINTRUST_FILE_INFO);
        FileData.pcwszFilePath = wszFileName;
        FileData.hFile = NULL;
        FileData.pgKnownSubject = NULL;

        /*
		WVTPolicyGUID specifies the policy to apply on the file
		WINTRUST_ACTION_GENERIC_VERIFY_V2 policy checks:

		1) The certificate used to sign the file chains up to a root
		certificate located in the trusted root certificate store. This
		implies that the identity of the publisher has been verified by
		a certification authority.

		2) In cases where user interface is displayed (which this example
		does not do), WinVerifyTrust will check for whether the
		end entity certificate is stored in the trusted publisher store,
		implying that the user trusts content from this publisher.

		3) The end entity certificate has sufficient permission to sign
		code, as indicated by the presence of a code signing EKU or no
		EKU.
		*/

        GUID WVTPolicyGUID = WINTRUST_ACTION_GENERIC_VERIFY_V2;
        WINTRUST_DATA WinTrustData;

        // Initialize the WinVerifyTrust input data structure.

        // Default all fields to 0.
        memset(&WinTrustData, 0, sizeof(WinTrustData));

        WinTrustData.cbStruct = sizeof(WinTrustData);

        // Use default code signing EKU.
        WinTrustData.pPolicyCallbackData = NULL;

        // No data to pass to SIP.
        WinTrustData.pSIPClientData = NULL;

        // Disable WVT UI.
        WinTrustData.dwUIChoice = WTD_UI_NONE;

        // No revocation checking.
        WinTrustData.fdwRevocationChecks = WTD_REVOKE_NONE;

        // Verify an embedded signature on a file.
        WinTrustData.dwUnionChoice = WTD_CHOICE_FILE;

        // Default verification.
        WinTrustData.dwStateAction = 0;

        // Not applicable for default verification of embedded signature.
        WinTrustData.hWVTStateData = NULL;

        // Not used.
        WinTrustData.pwszURLReference = NULL;

        // This is not applicable if there is no UI because it changes
        // the UI to accommodate running applications instead of
        // installing applications.
        WinTrustData.dwUIContext = 0;

        // Set pFile.
        WinTrustData.pFile = &FileData;

        if (DoSecondPass == FALSE)
        {
            //[BT 3618]: [Signature] Sometimes it takes a very long time to perform the signature check
            //La première fois on essaye de se servir du cache local pour aller plus vite
            //si ça échoue, on ne met pas ce flag à la 2ème passe, et ça ira chercher
            //sur Internet, ce qui prend plus de temps.
            WinTrustData.dwProvFlags = WTD_CACHE_ONLY_URL_RETRIEVAL;
        }

        // WinVerifyTrust verifies signatures as specified by the GUID
        // and Wintrust_Data.

        lStatus = WinVerifyTrust(
            0,
            &WVTPolicyGUID,
            &WinTrustData);

        switch (lStatus)
        {
            case ERROR_SUCCESS:
                /*
			Signed file:
			- Hash that represents the subject is trusted.

			- Trusted publisher without any verification errors.

			- UI was disabled in dwUIChoice. No publisher or
			time stamp chain errors.

			- UI was enabled in dwUIChoice and the user clicked
			"Yes" when asked to install and run the signed
			subject.
			*/
                break;

            case TRUST_E_NOSIGNATURE:
                // The file was not signed or had a signature
                // that was not valid.

                // Get the reason for no signature.
                dwLastError = GetLastError();
                if (TRUST_E_NOSIGNATURE == dwLastError ||
                    TRUST_E_SUBJECT_FORM_UNKNOWN == dwLastError ||
                    TRUST_E_PROVIDER_UNKNOWN == dwLastError)
                {
                    // The file was not signed.
                }
                else
                {
                    // The signature was not valid or there was an error
                    // opening the file.
                }
                break;

            case TRUST_E_EXPLICIT_DISTRUST:
                // The hash that represents the subject or the publisher
                // is not allowed by the admin or user.
                break;

            case TRUST_E_SUBJECT_NOT_TRUSTED:
                // The user clicked "No" when asked to install and run.
                break;

            case CRYPT_E_SECURITY_SETTINGS:
                /*
			The hash that represents the subject or the publisher
			was not explicitly trusted by the admin and the
			admin policy has disabled user trust. No signature,
			publisher or time stamp errors.
			*/
                break;

            case TRUST_E_BAD_DIGEST:
                /*
			The digital signature of the object did not verify.	ex : File has been modified
			*/
                break;

            case CERT_E_CHAINING:
                /*
			A certificate chain could not be built to a trusted root authority.
			*/
                //C'est le cas typique où le chainage n'est pas disponible dans le cache local
                //on tente une deuxième passe.
                DoSecondPass = TRUE;
                break;

            default:
                // The UI was disabled in dwUIChoice or the admin policy
                // has disabled user trust. lStatus contains the
                // publisher or time stamp chain error.
                DoSecondPass = TRUE;  //On tente quand même une 2ème passe, au cas où.
                break;
        }

        Count++;

    } while ((DoSecondPass == TRUE) && (Count < 2));  //Si la première passe a échoué, on en fait une 2ème (et uniquement une 2ème).

    return lStatus;
}

static BOOL SD_GetAuthenticodeInformation(LPCTSTR lpszFileName, PSPROG_SIGNATUREINFO pInfo)
{
    HCERTSTORE hStore = NULL;
    HCRYPTMSG hMsg = NULL;
    PCMSG_SIGNER_INFO pSignerInfo = NULL;
    DWORD dwSignerInfo;

    BOOL bRet = FALSE;

    __try
    {
        // as CryptQueryObject() only accept WCHAR file name, convert first
        WCHAR wszFileName[MAX_PATH];
#ifdef UNICODE
        if (!lstrcpynW(wszFileName, lpszFileName, MAX_PATH))
            __leave;
#else
        size_t RetSize;
        //if ( mbstowcs( wszFileName, lpszFileName, MAX_PATH) == -1)
        //Remplacé pour la certifié en:
        if (mbstowcs_s(&RetSize, wszFileName, MAX_PATH, lpszFileName, _TRUNCATE) != 0)
            __leave;
#endif
        //Retrieve the Message Handle and Store Handle
        DWORD dwEncoding, dwContentType, dwFormatType;
        if (!CryptQueryObject(CERT_QUERY_OBJECT_FILE, wszFileName, CERT_QUERY_CONTENT_FLAG_PKCS7_SIGNED_EMBED, CERT_QUERY_FORMAT_FLAG_BINARY, 0, &dwEncoding, &dwContentType, &dwFormatType, &hStore, &hMsg, NULL))
            __leave;

        //Get the length of SignerInfo
        if (!CryptMsgGetParam(hMsg, CMSG_SIGNER_INFO_PARAM, 0, NULL, &dwSignerInfo))
            __leave;

        // allocate the memory for SignerInfo
        pSignerInfo = (PCMSG_SIGNER_INFO)LocalAlloc(LPTR, dwSignerInfo);
        if (!pSignerInfo)
            __leave;

        // get the SignerInfo
        if (!CryptMsgGetParam(hMsg, CMSG_SIGNER_INFO_PARAM, 0, (PVOID)pSignerInfo, &dwSignerInfo))
            __leave;

        //get the Publisher from SignerInfo
        GetProgAndPublisherInfo(pSignerInfo, pInfo);

        //get the Certificate from SignerInfo
        GetCertificateInfo(hStore, pSignerInfo, pInfo);

        bRet = TRUE;
    }
    __finally
    {
        // release the memory
        if (pSignerInfo != NULL)
            LocalFree(pSignerInfo);
        if (hStore != NULL)
            CertCloseStore(hStore, 0);
        if (hMsg != NULL)
            CryptMsgClose(hMsg);
    }
    return bRet;
}

static VOID GetProgAndPublisherInfo(PCMSG_SIGNER_INFO pSignerInfo, PSPROG_SIGNATUREINFO pInfo)
{
    PSPC_SP_OPUS_INFO OpusInfo = NULL;
    DWORD dwData;

    __try
    {
        // query SPC_SP_OPUS_INFO_OBJID OID in Authenticated Attributes
        for (DWORD n = 0; n < pSignerInfo->AuthAttrs.cAttr; n++)
        {
            if (lstrcmpA(SPC_SP_OPUS_INFO_OBJID, pSignerInfo->AuthAttrs.rgAttr[n].pszObjId) == 0)
            {
                // get the length of SPC_SP_OPUS_INFO
                if (!CryptDecodeObject(ENCODING,
                                       SPC_SP_OPUS_INFO_OBJID,
                                       pSignerInfo->AuthAttrs.rgAttr[n].rgValue[0].pbData,
                                       pSignerInfo->AuthAttrs.rgAttr[n].rgValue[0].cbData,
                                       0,
                                       NULL,
                                       &dwData))
                    __leave;

                // allocate the memory for SPC_SP_OPUS_INFO
                OpusInfo = (PSPC_SP_OPUS_INFO)LocalAlloc(LPTR, dwData);
                if (!OpusInfo)
                    __leave;

                // get SPC_SP_OPUS_INFO structure
                if (!CryptDecodeObject(ENCODING,
                                       SPC_SP_OPUS_INFO_OBJID,
                                       pSignerInfo->AuthAttrs.rgAttr[n].rgValue[0].pbData,
                                       pSignerInfo->AuthAttrs.rgAttr[n].rgValue[0].cbData,
                                       0,
                                       OpusInfo,
                                       &dwData))
                    __leave;

                // copy the Program Name of SPC_SP_OPUS_INFO to the return variable
                if (OpusInfo->pwszProgramName)
                {
                    pInfo->lpszProgramName = AllocateAndCopyWideString(OpusInfo->pwszProgramName);
                }
                else
                    pInfo->lpszProgramName = NULL;

                // copy the Publisher Info of SPC_SP_OPUS_INFO to the return variable
                if (OpusInfo->pPublisherInfo)
                {
                    switch (OpusInfo->pPublisherInfo->dwLinkChoice)
                    {
                        case SPC_URL_LINK_CHOICE:
                            pInfo->lpszPublisherLink = AllocateAndCopyWideString(OpusInfo->pPublisherInfo->pwszUrl);
                            break;

                        case SPC_FILE_LINK_CHOICE:
                            pInfo->lpszPublisherLink = AllocateAndCopyWideString(OpusInfo->pPublisherInfo->pwszFile);
                            break;

                        default:
                            pInfo->lpszPublisherLink = NULL;
                            break;
                    }
                }
                else
                {
                    pInfo->lpszPublisherLink = NULL;
                }

                // copy the More Info of SPC_SP_OPUS_INFO to the return variable
                if (OpusInfo->pMoreInfo)
                {
                    switch (OpusInfo->pMoreInfo->dwLinkChoice)
                    {
                        case SPC_URL_LINK_CHOICE:
                            pInfo->lpszMoreInfoLink = AllocateAndCopyWideString(OpusInfo->pMoreInfo->pwszUrl);
                            break;

                        case SPC_FILE_LINK_CHOICE:
                            pInfo->lpszMoreInfoLink = AllocateAndCopyWideString(OpusInfo->pMoreInfo->pwszFile);
                            break;

                        default:
                            pInfo->lpszMoreInfoLink = NULL;
                            break;
                    }
                }
                else
                {
                    pInfo->lpszMoreInfoLink = NULL;
                }

                break;  // we have got the information, break
            }
        }
    }
    __finally
    {
        if (OpusInfo != NULL)
            LocalFree(OpusInfo);
    }
}

VOID GetCertificateInfo(HCERTSTORE hStore, PCMSG_SIGNER_INFO pSignerInfo, PSPROG_SIGNATUREINFO pInfo)
{
    PCCERT_CONTEXT pCertContext = NULL;

    OutputDebugStringA("TGBSYSDEP: => GetCertificateInfo");

    __try
    {
        CERT_INFO CertInfo;
        DWORD dwData;

        // query Signer Certificate in Certificate Store
        CertInfo.Issuer = pSignerInfo->Issuer;
        CertInfo.SerialNumber = pSignerInfo->SerialNumber;

        pCertContext = CertFindCertificateInStore(hStore,
                                                  ENCODING,
                                                  0,
                                                  CERT_FIND_SUBJECT_CERT,
                                                  (PVOID)&CertInfo,
                                                  NULL);
        if (!pCertContext)
        {
            OutputDebugStringA("TGBSYSDEP: GetCertificateInfo CheckPoint 1");
            __leave;
        }

        dwData = pCertContext->pCertInfo->SerialNumber.cbData;

        // SPROG_SIGNATUREINFO.cbSerialSize
        pInfo->cbSerialSize = dwData;

        // SPROG_SIGNATUREINFO.lpSerialNumber
        pInfo->lpSerialNumber = (LPBYTE)VirtualAlloc(NULL, dwData, MEM_COMMIT, PAGE_READWRITE);
        memcpy(pInfo->lpSerialNumber, pCertContext->pCertInfo->SerialNumber.pbData, dwData);

        // SPROG_SIGNATUREINFO.lpszIssuerName
        __try
        {
            // get the length of Issuer Name
            dwData = CertGetNameString(pCertContext,
                                       CERT_NAME_SIMPLE_DISPLAY_TYPE,
                                       CERT_NAME_ISSUER_FLAG,
                                       NULL,
                                       NULL,
                                       0);
            if (!dwData)
                __leave;

            // allocate the memory
            pInfo->lpszIssuerName = (LPTSTR)VirtualAlloc(NULL, dwData * sizeof(TCHAR), MEM_COMMIT, PAGE_READWRITE);
            if (!pInfo->lpszIssuerName)
                __leave;

            // get Issuer Name
            if (!(CertGetNameString(pCertContext,
                                    CERT_NAME_SIMPLE_DISPLAY_TYPE,
                                    CERT_NAME_ISSUER_FLAG,
                                    NULL,
                                    pInfo->lpszIssuerName,
                                    dwData)))
                __leave;
        }
        __finally
        {
        }

        // SPROG_SIGNATUREINFO.lpszSubjectName
        __try
        {
            //get the length of Subject Name
            dwData = CertGetNameString(pCertContext, CERT_NAME_SIMPLE_DISPLAY_TYPE, 0, NULL, NULL, 0);
            if (!dwData)
                __leave;

            // allocate the memory
            pInfo->lpszSubjectName = (LPTSTR)VirtualAlloc(NULL, dwData * sizeof(TCHAR), MEM_COMMIT, PAGE_READWRITE);
            if (!pInfo->lpszSubjectName)
                __leave;

            // get Subject Name
            if (!(CertGetNameString(pCertContext, CERT_NAME_SIMPLE_DISPLAY_TYPE, 0, NULL, pInfo->lpszSubjectName, dwData)))
                __leave;
        }
        __finally
        {
        }
    }
    __finally
    {
        if (pCertContext != NULL)
            CertFreeCertificateContext(pCertContext);
    }
    OutputDebugStringA("TGBSYSDEP: <= GetCertificateInfo");
}

LPWSTR AllocateAndCopyWideString(LPCWSTR inputString)
{
    LPWSTR outputString = NULL;

    outputString = (LPWSTR)LocalAlloc(LPTR,
                                      (wcslen(inputString) + 1) * sizeof(WCHAR));
    if (outputString != NULL)
    {
        lstrcpyW(outputString, inputString);
    }
    return outputString;
}

static PyObject* tgb_is_signed(PyObject* self, PyObject* args) {
    const char* path;
    SPROG_SIGNATUREINFO SignInfo;
    ZeroMemory(&SignInfo, sizeof(SignInfo));
    BOOL bRet = FALSE;

    if (!PyArg_ParseTuple(args, "s", &path)) {
        return NULL;
    }

    if (SD_VerifyEmbeddedSignature(path) == ERROR_SUCCESS) {
        if (SD_GetAuthenticodeInformation(path, &SignInfo)) {
            if (_tcsncicmp(SignInfo.lpszSubjectName, "TheGreenBow", 11) == 0
                || _tcsncicmp(SignInfo.lpszSubjectName, "SISTECH", 7) == 0) {
                return PyBool_FromLong(1);
            }
        }
    }

    return PyBool_FromLong(0);
}

static PyMethodDef TGBVerifierMethods[] = {
    {"is_signed", tgb_is_signed, METH_VARARGS, "Checks if the given DLL is signed"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef tgbverifiermodule = {
    PyModuleDef_HEAD_INIT,
    "tgb",
    NULL,
    -1,
    TGBVerifierMethods
};

PyMODINIT_FUNC PyInit_tgbverifier(void) {
    return PyModule_Create(&tgbverifiermodule);
}
