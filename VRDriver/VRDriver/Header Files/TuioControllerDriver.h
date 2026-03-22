#pragma once

#include "openvr_driver.h"
#include <string>
#include <mutex>

class TuioControllerDriver : public vr::ITrackedDeviceServerDriver
{
public:
    explicit TuioControllerDriver(const std::string& side);
    ~TuioControllerDriver() = default;

    // ── ITrackedDeviceServerDriver ──────────────────────────────────────────
    vr::EVRInitError Activate(uint32_t unObjectId) override;
    void             Deactivate() override;
    void             EnterStandby() override;
    void*            GetComponent(const char* pchComponentNameAndVersion) override;
    void             DebugRequest(const char* pchRequest, char* pchResponseBuffer,
                                  uint32_t unResponseBufferSize) override;
    vr::DriverPose_t GetPose() override;

    // ── Custom ──────────────────────────────────────────────────────────────
    void UpdatePose(float x, float y, float z,
                    float qw, float qx, float qy, float qz);

    const std::string& GetSide() const { return m_side; }
    const std::string& GetSerialNumber() const { return m_serialNumber; }

private:
    std::string  m_side;           // "left" or "right"
    std::string  m_serialNumber;
    uint32_t     m_deviceIndex = vr::k_unTrackedDeviceIndexInvalid;
    vr::PropertyContainerHandle_t m_propertyContainer = vr::k_ulInvalidPropertyContainer;

    mutable std::mutex   m_poseMutex;
    vr::DriverPose_t     m_pose;

    void InitDefaultPose();
};
