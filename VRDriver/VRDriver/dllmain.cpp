// dllmain.cpp : Defines the entry point for the DLL application.
#include "Header Files\pch.h"
#include "Header Files\TuioDriverProvider.h"

// ── DLL entry point (required by Windows) ───────────────────────────────────
BOOL APIENTRY DllMain(HMODULE hModule,
                      DWORD  ul_reason_for_call,
                      LPVOID lpReserved)
{
    switch (ul_reason_for_call)
    {
    case DLL_PROCESS_ATTACH:
    case DLL_THREAD_ATTACH:
    case DLL_THREAD_DETACH:
    case DLL_PROCESS_DETACH:
        break;
    }
    return TRUE;
}

// ── SteamVR driver factory (exported symbol) ────────────────────────────────
static TuioDriverProvider g_driverProvider;

extern "C" __declspec(dllexport)
void* HmdDriverFactory(const char* pInterfaceName, int* pReturnCode)
{
    if (0 == strcmp(pInterfaceName, vr::IServerTrackedDeviceProvider_Version))
    {
        return &g_driverProvider;
    }

    if (pReturnCode)
        *pReturnCode = vr::VRInitError_Init_InterfaceNotFound;

    return nullptr;
}
