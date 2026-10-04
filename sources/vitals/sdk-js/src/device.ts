// User-agent parsing for device/app metadata (best effort, no dependencies).
export interface DeviceInfo {
  os: string;
  browser: string;
  device: string;
  locale: string;
}

export function deviceInfo(ua: string = navigator.userAgent, locale: string = navigator.language): DeviceInfo {
  const android = /Android (\d+(?:\.\d+)?)/.exec(ua);
  const ios = /(?:iPhone|iPad|iPod).*? OS (\d+)[_.](\d+)/.exec(ua);
  const mac = /Mac OS X (\d+)[_.](\d+)/.exec(ua);
  const win = /Windows NT (\d+\.\d+)/.exec(ua);
  const os = android
    ? `Android ${android[1]}`
    : ios
      ? `iOS ${ios[1]}.${ios[2]}`
      : mac
        ? `macOS ${mac[1]}.${mac[2]}`
        : win
          ? `Windows ${win[1]}`
          : /Linux/.test(ua)
            ? "Linux"
            : "unknown";
  const edge = /Edg\/(\d+)/.exec(ua);
  const chrome = /(?:Chrome|CriOS)\/(\d+)/.exec(ua);
  const firefox = /(?:Firefox|FxiOS)\/(\d+)/.exec(ua);
  const safari = /Version\/(\d+).*Safari/.exec(ua);
  const browser = edge
    ? `Edge ${edge[1]}`
    : chrome
      ? `Chrome ${chrome[1]}`
      : firefox
        ? `Firefox ${firefox[1]}`
        : safari
          ? `Safari ${safari[1]}`
          : "unknown";
  const model = /Android [\d.]+; ([^;)]+?)(?: Build|\))/.exec(ua)?.[1]?.trim();
  const device = model && model !== "K" ? model : /iPhone/.test(ua) ? "iPhone" : /iPad/.test(ua) ? "iPad" : /Mobile/.test(ua) ? "mobile" : "desktop";
  return { os, browser, device, locale };
}
