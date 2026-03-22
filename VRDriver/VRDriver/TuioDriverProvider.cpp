#include "Header Files\pch.h"
#include "Header Files\TuioDriverProvider.h"
#include "Header Files\TuioControllerDriver.h"
#include "Header Files\PipeListener.h"

vr::EVRInitError TuioDriverProvider::Init(vr::IVRDriverContext* pDriverContext)
{
    VR_INIT_SERVER_DRIVER_CONTEXT(pDriverContext);

    // ── Create controllers ──────────────────────────────────────────────────
    m_leftController  = std::make_unique<TuioControllerDriver>("left");
    m_rightController = std::make_unique<TuioControllerDriver>("right");

    // Register with SteamVR
    vr::VRServerDriverHost()->TrackedDeviceAdded(
        m_leftController->GetSerialNumber().c_str(),
        vr::TrackedDeviceClass_Controller,
        m_leftController.get());

    vr::VRServerDriverHost()->TrackedDeviceAdded(
        m_rightController->GetSerialNumber().c_str(),
        vr::TrackedDeviceClass_Controller,
        m_rightController.get());

    // ── Create pipe listeners ───────────────────────────────────────────────
    m_leftPipe  = std::make_unique<PipeListener>(
        R"(\\.\pipe\tuio_controller_left)", m_leftController.get());
    m_rightPipe = std::make_unique<PipeListener>(
        R"(\\.\pipe\tuio_controller_right)", m_rightController.get());

    m_leftPipe->Start();
    m_rightPipe->Start();

    return vr::VRInitError_None;
}

void TuioDriverProvider::Cleanup()
{
    m_leftPipe.reset();
    m_rightPipe.reset();
    m_leftController.reset();
    m_rightController.reset();

    VR_CLEANUP_SERVER_DRIVER_CONTEXT();
}

const char* const* TuioDriverProvider::GetInterfaceVersions()
{
    return vr::k_InterfaceVersions;
}

void TuioDriverProvider::RunFrame()
{
    // Pose updates are pushed by the pipe listener threads directly,
    // so nothing needs to happen here.
}

bool TuioDriverProvider::ShouldBlockStandbyMode()
{
    return false;
}

void TuioDriverProvider::EnterStandby() {}
void TuioDriverProvider::LeaveStandby() {}
