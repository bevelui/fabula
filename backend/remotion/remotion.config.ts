import {Config} from '@remotion/cli/config';

Config.setVideoImageFormat('jpeg');
Config.setOverwriteOutput(true);
Config.setConcurrency(null); // use all cores

// Headless-Chrome stability when rendering as root inside Docker (Remotion v4.0.42+).
// Guarded: only on Linux, and only if the setter exists on this version — so it can
// never break local (Windows/macOS) rendering if the API name differs.
if (process.platform === 'linux') {
  const c = Config as unknown as Record<string, (v: boolean) => void>;
  for (const name of ['setChromiumMultiProcessOnLinux', 'setEnableMultiprocessOnLinux']) {
    if (typeof c[name] === 'function') {
      c[name](true);
      break;
    }
  }
}
