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

        // ── High-score DTO ────────────────────────────────────────────────────

        private sealed class HighScoreFileDto
        {
            public List<HighScoreEntryDto> scores { get; set; }
        }

        private sealed class HighScoreEntryDto
        {
            public int id { get; set; }
            public int high_score { get; set; }
        }

        // ── JSON options ──────────────────────────────────────────────────────

        private static readonly JsonSerializerOptions ReadOpts = new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true,
        };

        private static readonly JsonSerializerOptions WriteOpts = new JsonSerializerOptions
        {
            WriteIndented = true,
        };

        // ── High-score file path (same folder as admin_users.json) ─────────

        private static string HighScoresJsonPath =>
            Path.Combine(
                Path.GetDirectoryName(AppConfig.AdminUsersJsonPath) ?? AppConfig.RepoRoot,
                "high_scores.json");

        // ── Public API ────────────────────────────────────────────────────────

        /// <summary>Load the high score for a single user. Returns 0 if not found.</summary>
        public static int LoadHighScore(int userId)
        {
            try
            {
                string path = HighScoresJsonPath;
                if (!File.Exists(path))
                    return 0;

                string json = File.ReadAllText(path);
                var dto = JsonSerializer.Deserialize<HighScoreFileDto>(json, ReadOpts);
                if (dto?.scores == null)
                    return 0;

                var entry = dto.scores.FirstOrDefault(e => e != null && e.id == userId);
                return entry?.high_score ?? 0;
            }
            catch
            {
                return 0;
            }
        }

        /// <summary>
        /// Persist <paramref name="score"/> for <paramref name="userId"/> only if it beats
        /// the stored value.  Returns the new persisted high score.
        /// </summary>
        public static int SaveHighScore(int userId, int score)
        {
            try
            {
                string path = HighScoresJsonPath;

                // Load existing records
                HighScoreFileDto dto = null;
                if (File.Exists(path))
                {
                    try
                    {
                        string json = File.ReadAllText(path);
                        dto = JsonSerializer.Deserialize<HighScoreFileDto>(json, ReadOpts);
                    }
                    catch { }
                }

                dto ??= new HighScoreFileDto { scores = new List<HighScoreEntryDto>() };
                dto.scores ??= new List<HighScoreEntryDto>();

                var existing = dto.scores.FirstOrDefault(e => e != null && e.id == userId);
                if (existing == null)
                {
                    existing = new HighScoreEntryDto { id = userId, high_score = 0 };
                    dto.scores.Add(existing);
                }

                // Only update when the new score is higher
                if (score > existing.high_score)
                    existing.high_score = score;

                // Write back sorted by id
                dto.scores = dto.scores
                    .Where(e => e != null)
                    .OrderBy(e => e.id)
                    .ToList();

                string dir = Path.GetDirectoryName(path);
                if (!string.IsNullOrEmpty(dir))
                    Directory.CreateDirectory(dir);

                File.WriteAllText(path, JsonSerializer.Serialize(dto, WriteOpts));

                return existing.high_score;
            }
            catch
            {
                return score;
            }
        }

        // ── Existing user-store logic (unchanged) ─────────────────────────────

        private static readonly string[] NameParts =
        {
            "Nova", "River", "Sky", "Echo", "Morgan", "Quinn", "Phoenix", "Sage",
            "Rowan", "Indigo", "Ash", "Jules", "Reese", "Blair", "Eden", "Atlas",
            "Lyra", "Cyrus", "Luna", "Orion", "Zephyr", "Dawn", "Storm", "Frost",
            "Ember", "Sol", "Dusk", "Cloud", "Skylar", "Azure", "Slate", "Terra"
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
            int n = 40;
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