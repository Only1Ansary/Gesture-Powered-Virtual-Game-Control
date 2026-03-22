#include "Header Files\pch.h"
#include "Header Files\TuioControllerDriver.h"

TuioControllerDriver::TuioControllerDriver(const std::string& side)
    : m_side(side)
{
    m_serialNumber = "tuio_controller_" + m_side;
    InitDefaultPose();
}

// ═══════════════════════════════════════════════════════════════════════════════
//  ITrackedDeviceServerDriver
// ═══════════════════════════════════════════════════════════════════════════════

vr::EVRInitError TuioControllerDriver::Activate(uint32_t unObjectId)
{
    m_deviceIndex = unObjectId;
    m_propertyContainer = vr::VRProperties()->TrackedDeviceToPropertyContainer(unObjectId);

    // ── Device classification ───────────────────────────────────────────────
    vr::VRProperties()->SetInt32Property(m_propertyContainer,
        vr::Prop_DeviceClass_Int32, vr::TrackedDeviceClass_Controller);

    vr::VRProperties()->SetStringProperty(m_propertyContainer,
        vr::Prop_ControllerType_String, "knuckles");

    vr::VRProperties()->SetStringProperty(m_propertyContainer,
        vr::Prop_ManufacturerName_String, "Valve");

    // ── Side-specific properties ────────────────────────────────────────────
    if (m_side == "left")
    {
        vr::VRProperties()->SetStringProperty(m_propertyContainer,
            vr::Prop_ModelNumber_String, "Knuckles Left");
        vr::VRProperties()->SetInt32Property(m_propertyContainer,
            vr::Prop_ControllerRoleHint_Int32, vr::TrackedControllerRole_LeftHand);
    }
    else
    {
        vr::VRProperties()->SetStringProperty(m_propertyContainer,
            vr::Prop_ModelNumber_String, "Knuckles Right");
        vr::VRProperties()->SetInt32Property(m_propertyContainer,
            vr::Prop_ControllerRoleHint_Int32, vr::TrackedControllerRole_RightHand);
    }

    // ── Input profile ───────────────────────────────────────────────────────
    vr::VRProperties()->SetStringProperty(m_propertyContainer,
        vr::Prop_InputProfilePath_String,
        "{indexcontroller}/input/index_controller_profile.json");

    // ── Misc ────────────────────────────────────────────────────────────────
    vr::VRProperties()->SetStringProperty(m_propertyContainer,
        vr::Prop_SerialNumber_String, m_serialNumber.c_str());

    vr::VRProperties()->SetStringProperty(m_propertyContainer,
        vr::Prop_RenderModelName_String,
        (m_side == "left")
            ? "{indexcontroller}valve_controller_knu_1_0_left"
            : "{indexcontroller}valve_controller_knu_1_0_right");

    return vr::VRInitError_None;
}

void TuioControllerDriver::Deactivate()
{
    m_deviceIndex = vr::k_unTrackedDeviceIndexInvalid;
}

void TuioControllerDriver::EnterStandby() {}

void* TuioControllerDriver::GetComponent(const char* /*pchComponentNameAndVersion*/)
{
    return nullptr;
}

void TuioControllerDriver::DebugRequest(const char* /*pchRequest*/,
                                         char* pchResponseBuffer,
                                         uint32_t unResponseBufferSize)
{
    if (unResponseBufferSize > 0)
        pchResponseBuffer[0] = '\0';
}

vr::DriverPose_t TuioControllerDriver::GetPose()
{
    std::lock_guard<std::mutex> lock(m_poseMutex);
    return m_pose;
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Pose helpers
// ═══════════════════════════════════════════════════════════════════════════════

void TuioControllerDriver::InitDefaultPose()
{
    std::memset(&m_pose, 0, sizeof(m_pose));

    m_pose.poseIsValid            = true;
    m_pose.result                 = vr::TrackingResult_Running_OK;
    m_pose.deviceIsConnected      = true;
    m_pose.poseTimeOffset         = 0.0;
    m_pose.willDriftInYaw         = false;
    m_pose.shouldApplyHeadModel   = false;

    // Identity quaternion
    m_pose.qWorldFromDriverRotation.w = 1.0;
    m_pose.qWorldFromDriverRotation.x = 0.0;
    m_pose.qWorldFromDriverRotation.y = 0.0;
    m_pose.qWorldFromDriverRotation.z = 0.0;

    m_pose.qDriverFromHeadRotation.w = 1.0;
    m_pose.qDriverFromHeadRotation.x = 0.0;
    m_pose.qDriverFromHeadRotation.y = 0.0;
    m_pose.qDriverFromHeadRotation.z = 0.0;

    // Rotation of the device itself
    m_pose.qRotation.w = 1.0;
    m_pose.qRotation.x = 0.0;
    m_pose.qRotation.y = 0.0;
    m_pose.qRotation.z = 0.0;

    // Position at origin
    m_pose.vecPosition[0] = 0.0;
    m_pose.vecPosition[1] = 0.0;
    m_pose.vecPosition[2] = 0.0;
}

void TuioControllerDriver::UpdatePose(float x, float y, float z,
                                       float qw, float qx, float qy, float qz)
{
    {
        std::lock_guard<std::mutex> lock(m_poseMutex);
        m_pose.vecPosition[0] = x;
        m_pose.vecPosition[1] = y;
        m_pose.vecPosition[2] = z;
        m_pose.qRotation.w = qw;
        m_pose.qRotation.x = qx;
        m_pose.qRotation.y = qy;
        m_pose.qRotation.z = qz;
    }

    if (m_deviceIndex != vr::k_unTrackedDeviceIndexInvalid)
    {
        vr::VRServerDriverHost()->TrackedDevicePoseUpdated(
            m_deviceIndex, GetPose(), sizeof(vr::DriverPose_t));
    }
}
