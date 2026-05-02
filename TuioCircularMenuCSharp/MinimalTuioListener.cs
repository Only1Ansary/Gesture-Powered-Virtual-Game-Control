using System;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;

namespace TuioCircularMenu
{
    public class MinimalTuioListener
    {
        private UdpClient udpClient;
        private Thread thread;
        private bool running;
        public event Action<int, float> OnMarkerRotated;

        public void Start(int port = 3333)
        {
            udpClient = new UdpClient(port);
            running = true;
            thread = new Thread(Listen);
            thread.IsBackground = true;
            thread.Start();
        }

        public void Stop()
        {
            running = false;
            if (udpClient != null) udpClient.Close();
        }

        private void Listen()
        {
            IPEndPoint ep = new IPEndPoint(IPAddress.Any, 0);
            while (running)
            {
                try
                {
                    if (udpClient == null) break;
                    byte[] data = udpClient.Receive(ref ep);
                    ParseOsc(data);
                }
                catch { }
            }
        }

        private void ParseOsc(byte[] data)
        {
            int index = 0;
            string address = ReadString(data, ref index);
            if (address == "#bundle")
            {
                index += 8; // skip time tag
                while (index < data.Length)
                {
                    int length = ReadInt(data, ref index);
                    int nextIndex = index + length;
                    if (nextIndex > data.Length) break;
                    ParseMessage(data, ref index);
                    index = nextIndex;
                }
            }
            else
            {
                ParseMessage(data, ref index, address);
            }
        }

        private void ParseMessage(byte[] data, ref int index, string address = null)
        {
            if (address == null)
                address = ReadString(data, ref index);

            if (address == "/tuio/2Dobj")
            {
                string typeTags = ReadString(data, ref index);
                if (typeTags.StartsWith(","))
                {
                    string command = ReadString(data, ref index);
                    if (command == "set")
                    {
                        int sessionId = ReadInt(data, ref index);
                        int classId = ReadInt(data, ref index); // Marker ID
                        float x = ReadFloat(data, ref index);
                        float y = ReadFloat(data, ref index);
                        float a = ReadFloat(data, ref index); // Angle

                        if (OnMarkerRotated != null) OnMarkerRotated(classId, a);
                    }
                }
            }
        }

        private string ReadString(byte[] data, ref int index)
        {
            int start = index;
            while (index < data.Length && data[index] != 0) index++;
            string s = Encoding.ASCII.GetString(data, start, index - start);
            index++; // skip null
            while (index % 4 != 0) index++; // pad to 4 bytes
            return s;
        }

        private int ReadInt(byte[] data, ref int index)
        {
            if (index + 4 > data.Length) return 0;
            if (BitConverter.IsLittleEndian)
            {
                byte[] rev = { data[index + 3], data[index + 2], data[index + 1], data[index] };
                int i = BitConverter.ToInt32(rev, 0);
                index += 4;
                return i;
            }
            else
            {
                int i = BitConverter.ToInt32(data, index);
                index += 4;
                return i;
            }
        }

        private float ReadFloat(byte[] data, ref int index)
        {
            if (index + 4 > data.Length) return 0f;
            if (BitConverter.IsLittleEndian)
            {
                byte[] rev = { data[index + 3], data[index + 2], data[index + 1], data[index] };
                float f = BitConverter.ToSingle(rev, 0);
                index += 4;
                return f;
            }
            else
            {
                float f = BitConverter.ToSingle(data, index);
                index += 4;
                return f;
            }
        }
    }
}
