using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace FruitNinjaGame
{
    /// <summary>
    /// Listens to TUIO /tuio/2Dobj packets over UDP OSC and emits marker events.
    /// This is a lightweight OSC decoder for the message shapes used by TUIO.
    /// </summary>
    public sealed class TuioAdapter : IDisposable
    {
        private readonly string _host;
        private readonly int _port;
        private readonly Action<int> _onMarkerDetected;
        private readonly Action<int> _onMarkerRemoved;
        private readonly Action<string, int> _onMarkerRotated;
        private readonly Action<int, float, float>? _onMarkerMoved;
        private readonly float _rotationThresholdRad;

        private UdpClient? _udp;
        private CancellationTokenSource? _cts;
        private Task? _listenTask;
        private bool _running;
        private readonly object _sync = new();

        private readonly Dictionary<int, float> _lastAngleByFid = new();
        private readonly Dictionary<int, int> _fidBySessionId = new();
        private readonly HashSet<int> _prevAliveSessionIds = new();

        public TuioAdapter(
            string host,
            int port,
            Action<int> onMarkerDetected,
            Action<int> onMarkerRemoved,
            Action<string, int> onMarkerRotated,
            float rotationThresholdRad = 0.45f,
            Action<int, float, float>? onMarkerMoved = null)
        {
            _host = host;
            _port = port;
            _onMarkerDetected = onMarkerDetected;
            _onMarkerRemoved = onMarkerRemoved;
            _onMarkerRotated = onMarkerRotated;
            _onMarkerMoved = onMarkerMoved;
            _rotationThresholdRad = Math.Abs(rotationThresholdRad);
        }

        public void Start()
        {
            if (_running) return;

            _cts = new CancellationTokenSource();
            _udp = new UdpClient(new IPEndPoint(IPAddress.Any, _port));
            _listenTask = Task.Run(() => ListenLoop(_cts.Token), _cts.Token);
            _running = true;
        }

        public void Stop()
        {
            if (!_running) return;

            try { _cts?.Cancel(); } catch { }
            try { _udp?.Close(); } catch { }
            try { _listenTask?.Wait(500); } catch { }

            _listenTask = null;
            _cts?.Dispose();
            _cts = null;
            _udp?.Dispose();
            _udp = null;
            _running = false;
            lock (_sync)
            {
                _lastAngleByFid.Clear();
                _fidBySessionId.Clear();
                _prevAliveSessionIds.Clear();
            }
        }

        public void Dispose()
        {
            Stop();
        }

        private async Task ListenLoop(CancellationToken token)
        {
            while (!token.IsCancellationRequested)
            {
                UdpReceiveResult packet;
                try
                {
                    if (_udp == null) break;
                    packet = await _udp.ReceiveAsync(token);
                }
                catch (OperationCanceledException)
                {
                    break;
                }
                catch
                {
                    if (token.IsCancellationRequested) break;
                    continue;
                }

                try
                {
                    ParseOscPacket(packet.Buffer, 0, packet.Buffer.Length);
                }
                catch
                {
                    // Keep listener alive even if one malformed packet arrives.
                }
            }
        }

        private void ParseOscPacket(byte[] data, int offset, int length)
        {
            if (length <= 0 || offset < 0 || offset + length > data.Length) return;

            if (IsBundle(data, offset, length))
            {
                ParseBundle(data, offset, length);
            }
            else
            {
                ParseMessage(data, offset, length);
            }
        }

        private static bool IsBundle(byte[] data, int offset, int length)
        {
            const string bundleTag = "#bundle";
            if (length < 8) return false;
            for (int i = 0; i < bundleTag.Length; i++)
            {
                if (data[offset + i] != bundleTag[i]) return false;
            }
            return data[offset + bundleTag.Length] == 0;
        }

        private void ParseBundle(byte[] data, int offset, int length)
        {
            int cursor = offset;
            cursor += Pad4(ReadOscString(data, ref cursor).bytesRead);
            cursor += 8; // timetag

            int end = offset + length;
            while (cursor + 4 <= end)
            {
                int elemLen = ReadInt32BE(data, ref cursor);
                if (elemLen <= 0 || cursor + elemLen > end) break;
                ParseOscPacket(data, cursor, elemLen);
                cursor += elemLen;
            }
        }

        private void ParseMessage(byte[] data, int offset, int length)
        {
            int cursor = offset;
            int end = offset + length;

            var (address, addrBytes) = ReadOscString(data, ref cursor);
            cursor = offset + Pad4(addrBytes);
            if (cursor >= end) return;

            var (typeTags, typeBytes) = ReadOscString(data, ref cursor);
            cursor = offset + Pad4(addrBytes) + Pad4(typeBytes);
            if (string.IsNullOrEmpty(typeTags) || typeTags[0] != ',') return;

            var args = new List<object>();
            for (int i = 1; i < typeTags.Length; i++)
            {
                if (cursor > end) break;
                switch (typeTags[i])
                {
                    case 'i':
                        if (cursor + 4 > end) return;
                        args.Add(ReadInt32BE(data, ref cursor));
                        break;
                    case 'f':
                        if (cursor + 4 > end) return;
                        args.Add(ReadFloatBE(data, ref cursor));
                        break;
                    case 's':
                        {
                            var (s, read) = ReadOscString(data, ref cursor);
                            args.Add(s);
                            cursor += Pad4(read) - read;
                            break;
                        }
                    default:
                        return;
                }
            }

            if (!string.Equals(address, "/tuio/2Dobj", StringComparison.Ordinal)) return;
            if (args.Count == 0 || args[0] is not string cmd) return;

            if (string.Equals(cmd, "set", StringComparison.Ordinal))
            {
                HandleSet(args);
            }
            else if (string.Equals(cmd, "alive", StringComparison.Ordinal))
            {
                HandleAlive(args);
            }
        }

        private void HandleSet(List<object> args)
        {
            // set: [ "set", s_id, class_id(fid), x, y, angle, ... ]
            if (args.Count < 6) return;

            int sid = Convert.ToInt32(args[1]);
            int fid = Convert.ToInt32(args[2]);
            float x = Convert.ToSingle(args[3]);
            float y = Convert.ToSingle(args[4]);
            float angle = Convert.ToSingle(args[5]);

            _onMarkerMoved?.Invoke(fid, x, y);

            lock (_sync)
            {
                _fidBySessionId[sid] = fid;

                bool newlySeen = !_lastAngleByFid.ContainsKey(fid);
                if (newlySeen)
                {
                    _lastAngleByFid[fid] = angle;
                    _onMarkerDetected(fid);
                    return;
                }

                float prev = _lastAngleByFid[fid];
                float delta = NormalizeAngleDelta(angle - prev);
                _lastAngleByFid[fid] = angle;

                if (Math.Abs(delta) >= _rotationThresholdRad)
                {
                    _onMarkerRotated(delta > 0f ? "right" : "left", fid);
                }
            }
        }

        private void HandleAlive(List<object> args)
        {
            // alive: [ "alive", s_id1, s_id2, ... ]
            var currentAlive = new HashSet<int>();
            for (int i = 1; i < args.Count; i++)
            {
                currentAlive.Add(Convert.ToInt32(args[i]));
            }

            lock (_sync)
            {
                if (_prevAliveSessionIds.Count > 0)
                {
                    foreach (int previousSid in _prevAliveSessionIds)
                    {
                        if (currentAlive.Contains(previousSid)) continue;

                        if (_fidBySessionId.TryGetValue(previousSid, out int removedFid))
                        {
                            _fidBySessionId.Remove(previousSid);
                            _lastAngleByFid.Remove(removedFid);
                            _onMarkerRemoved(removedFid);
                        }
                    }
                }

                _prevAliveSessionIds.Clear();
                foreach (int sid in currentAlive) _prevAliveSessionIds.Add(sid);
            }
        }

        private static (string value, int bytesRead) ReadOscString(byte[] data, ref int cursor)
        {
            int start = cursor;
            while (cursor < data.Length && data[cursor] != 0) cursor++;
            string value = Encoding.ASCII.GetString(data, start, cursor - start);
            if (cursor < data.Length) cursor++; // null terminator
            return (value, cursor - start);
        }

        private static int Pad4(int n) => (n + 3) & ~3;

        private static int ReadInt32BE(byte[] data, ref int cursor)
        {
            int value =
                (data[cursor] << 24) |
                (data[cursor + 1] << 16) |
                (data[cursor + 2] << 8) |
                data[cursor + 3];
            cursor += 4;
            return value;
        }

        private static float ReadFloatBE(byte[] data, ref int cursor)
        {
            byte[] buf = new byte[4];
            buf[0] = data[cursor + 3];
            buf[1] = data[cursor + 2];
            buf[2] = data[cursor + 1];
            buf[3] = data[cursor];
            cursor += 4;
            return BitConverter.ToSingle(buf, 0);
        }

        private static float NormalizeAngleDelta(float delta)
        {
            while (delta > MathF.PI) delta -= 2f * MathF.PI;
            while (delta < -MathF.PI) delta += 2f * MathF.PI;
            return delta;
        }
    }
}
