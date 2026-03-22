#pragma once

#include "openvr_driver.h"
#include <memory>
#include "PipeListener.h"
#include "TuioControllerDriver.h"

class TuioControllerDriver;
class PipeListener;

class TuioDriverProvider : public vr::IServerTrackedDeviceProvider
{
public:
    // ── IServerTrackedDeviceProvider ─────────────────────────────────────────
    vr::EVRInitError Init(vr::IVRDriverContext* pDriverContext) override;
    void             Cleanup() override;
    const char* const* GetInterfaceVersions() override;
    void             RunFrame() override;
    bool             ShouldBlockStandbyMode() override;
    void             EnterStandby() override;
    void             LeaveStandby() override;

private:
    std::unique_ptr<TuioControllerDriver> m_leftController;
    std::unique_ptr<TuioControllerDriver> m_rightController;
    std::unique_ptr<PipeListener>         m_leftPipe;
    std::unique_ptr<PipeListener>         m_rightPipe;
};
