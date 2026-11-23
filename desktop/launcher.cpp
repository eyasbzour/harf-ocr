// HarfOCR.exe: starts the program as its shortcuts do, so it can be opened from its folder too.
// It runs python\pythonw.exe on app\desktop\app.py next to itself, then exits (desktop\build.ps1 builds it).
#include <windows.h>
#include <string>

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int) {
    wchar_t self[MAX_PATH];
    DWORD n = GetModuleFileNameW(nullptr, self, MAX_PATH);
    std::wstring dir(self, n);
    dir.resize(dir.find_last_of(L'\\'));
    std::wstring py = dir + L"\\python\\pythonw.exe";
    std::wstring cmd = L"\"" + py + L"\" \"" + dir + L"\\app\\desktop\\app.py\"";

    STARTUPINFOW si{sizeof si};
    PROCESS_INFORMATION pi{};
    if (!CreateProcessW(py.c_str(), cmd.data(), nullptr, nullptr, FALSE, 0, nullptr, dir.c_str(), &si, &pi)) {
        MessageBoxW(nullptr, (L"\u062A\u0639\u0630\u0631 \u062A\u0634\u063A\u064A\u0644 \u0627\u0644\u0628\u0631\u0646\u0627\u0645\u062C:\n" + py).c_str(),
                    L"Harf OCR", MB_ICONERROR | MB_RTLREADING | MB_RIGHT);
        return 1;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
}
