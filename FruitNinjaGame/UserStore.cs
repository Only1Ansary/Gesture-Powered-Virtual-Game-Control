#nullable disable
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;

namespace FruitNinjaGame
{
    /// <summary>Persist marker id + display name in admin_users.json (Python user_store parity).</summary>
    public static class UserStore
    {
        private sealed class FileDto
        {
            public List<EntryDto> users { get; set; }
        }

        private sealed class EntryDto
        {
            public int id { get; set; }
            public string name { get; set; }
        }

        private static readonly JsonSerializerOptions ReadOpts = new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true,
        };

        private static readonly JsonSerializerOptions WriteOpts = new JsonSerializerOptions
        {
            WriteIndented = true,
        };

        private static readonly string[] NameParts =
        {
            "Nova", "River", "Sky", "Echo", "Morgan", "Quinn", "Phoenix", "Sage",
            "Rowan", "Indigo", "Ash", "Jules", "Reese", "Blair", "Eden",
        };

        public static Dictionary<int, UserProfile> LoadUsers()
        {
            string path = AppConfig.AdminUsersJsonPath;
            if (!File.Exists(path))
                return DefaultFromCharacterMap();

            try
            {
                string json = File.ReadAllText(path);
                var dto = JsonSerializer.Deserialize<FileDto>(json, ReadOpts);
                if (dto?.users == null || dto.users.Count == 0)
                    return DefaultFromCharacterMap();

                var o = new Dictionary<int, UserProfile>();
                foreach (var row in dto.users)
                {
                    if (row == null) continue;
                    o[row.id] = CharacterMap.BuildUserProfile(row.id, row.name ?? "User");
                }

                if (o.Count == 0)
                    return DefaultFromCharacterMap();
                return o.OrderBy(kv => kv.Key).ToDictionary(kv => kv.Key, kv => kv.Value);
            }
            catch
            {
                return DefaultFromCharacterMap();
            }
        }

        public static void SaveUsers(Dictionary<int, UserProfile> users)
        {
            try
            {
                var dto = new FileDto
                {
                    users = users.OrderBy(kv => kv.Key)
                        .Select(kv => new EntryDto { id = kv.Key, name = kv.Value.Name })
                        .ToList(),
                };
                string path = AppConfig.AdminUsersJsonPath;
                string dir = Path.GetDirectoryName(path);
                if (!string.IsNullOrEmpty(dir))
                    Directory.CreateDirectory(dir);
                File.WriteAllText(path, JsonSerializer.Serialize(dto, WriteOpts));
            }
            catch { }
        }

        public static int NextFreeMarkerId(Dictionary<int, UserProfile> users)
        {
            int n = 0;
            while (users.ContainsKey(n))
                n++;
            return n;
        }

        public static string RandomDisplayName()
        {
            var rng = new Random();
            int a = rng.Next(NameParts.Length);
            int b = rng.Next(NameParts.Length - 1);
            if (b >= a) b++;
            return $"{NameParts[a]} {NameParts[b]}";
        }

        private static Dictionary<int, UserProfile> DefaultFromCharacterMap()
        {
            var src = CharacterMap.GetAllUsers();
            var o = new Dictionary<int, UserProfile>();
            foreach (var kv in src.OrderBy(k => k.Key))
                o[kv.Key] = CharacterMap.BuildUserProfile(kv.Key, kv.Value.Name);
            return o;
        }
    }
}
