#include "Header Files\pch.h"
#include "Header Files\PipeListener.h"
#include "Header Files\TuioControllerDriver.h"

// 7 floats: x, y, z, qw, qx, qy, qz
static constexpr DWORD PACKET_SIZE = 7 * sizeof(float);   // 28 bytes

PipeListener::PipeListener(const std::string& pipeName, TuioControllerDriver* controller)
    : m_pipeName(pipeName)
    , m_controller(controller)
{
    m_hStopEvent = CreateEventA(nullptr, TRUE, FALSE, nullptr);
}

PipeListener::~PipeListener()
{
    Stop();
    if (m_hStopEvent)
        CloseHandle(m_hStopEvent);
}

void PipeListener::Start()
{
    if (m_running.load())
        return;

    m_running.store(true);
    ResetEvent(m_hStopEvent);
    m_thread = std::thread(&PipeListener::ThreadFunc, this);
}

void PipeListener::Stop()
{
    if (!m_running.load())
        return;

    m_running.store(false);

    // Signal the stop event so ConnectNamedPipe (via overlapped) can wake up
    if (m_hStopEvent)
        SetEvent(m_hStopEvent);

    // If the pipe is waiting for a connection, cancel it
    if (m_hPipe != INVALID_HANDLE_VALUE)
        CancelIoEx(m_hPipe, nullptr);

    if (m_thread.joinable())
        m_thread.join();

    if (m_hPipe != INVALID_HANDLE_VALUE)
    {
        CloseHandle(m_hPipe);
        m_hPipe = INVALID_HANDLE_VALUE;
    }
}

void PipeListener::ThreadFunc()
{
    while (m_running.load())
    {
        // ── Create the named pipe ───────────────────────────────────────────
        m_hPipe = CreateNamedPipeA(
            m_pipeName.c_str(),
            PIPE_ACCESS_INBOUND | FILE_FLAG_OVERLAPPED,
            PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT,
            1,                  // max instances
            0,                  // out buffer
            PACKET_SIZE * 16,   // in buffer
            0,                  // default timeout
            nullptr             // security
        );

        if (m_hPipe == INVALID_HANDLE_VALUE)
        {
            Sleep(1000);
            continue;
        }

        // ── Wait for a client (Python app) using overlapped I/O ─────────────
        OVERLAPPED ov{};
        ov.hEvent = CreateEventA(nullptr, TRUE, FALSE, nullptr);

        BOOL connected = ConnectNamedPipe(m_hPipe, &ov);
        if (!connected)
        {
            DWORD err = GetLastError();
            if (err == ERROR_IO_PENDING)
            {
                // Wait for either client connection or stop signal
                HANDLE events[2] = { ov.hEvent, m_hStopEvent };
                DWORD waitResult = WaitForMultipleObjects(2, events, FALSE, INFINITE);

                if (waitResult != WAIT_OBJECT_0)
                {
                    // Stop was signalled or error
                    CancelIo(m_hPipe);
                    CloseHandle(ov.hEvent);
                    CloseHandle(m_hPipe);
                    m_hPipe = INVALID_HANDLE_VALUE;
                    break;
                }
            }
            else if (err != ERROR_PIPE_CONNECTED)
            {
                // Real error
                CloseHandle(ov.hEvent);
                CloseHandle(m_hPipe);
                m_hPipe = INVALID_HANDLE_VALUE;
                Sleep(500);
                continue;
            }
        }

        CloseHandle(ov.hEvent);

        // ── Read loop ───────────────────────────────────────────────────────
        char buffer[PACKET_SIZE];
        while (m_running.load())
        {
            DWORD bytesRead = 0;
            BOOL ok = ReadFile(m_hPipe, buffer, PACKET_SIZE, &bytesRead, nullptr);
            if (!ok || bytesRead != PACKET_SIZE)
                break;   // pipe broken or partial read → reconnect

            float* f = reinterpret_cast<float*>(buffer);
            m_controller->UpdatePose(f[0], f[1], f[2], f[3], f[4], f[5], f[6]);
        }

        // ── Client disconnected – tear down and recreate pipe ───────────────
        DisconnectNamedPipe(m_hPipe);
        CloseHandle(m_hPipe);
        m_hPipe = INVALID_HANDLE_VALUE;
    }
}
