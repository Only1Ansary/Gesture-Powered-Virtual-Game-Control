#pragma once

#include <string>
#include <thread>
#include <atomic>
#include <windows.h>

class TuioControllerDriver;  // forward declaration

class PipeListener
{
public:
    PipeListener(const std::string& pipeName, TuioControllerDriver* controller);
    ~PipeListener();

    void Start();
    void Stop();

private:
    void ThreadFunc();

    std::string            m_pipeName;
    TuioControllerDriver*  m_controller;
    std::atomic<bool>      m_running{ false };
    std::thread            m_thread;
    HANDLE                 m_hPipe = INVALID_HANDLE_VALUE;
    HANDLE                 m_hStopEvent = nullptr;
};
