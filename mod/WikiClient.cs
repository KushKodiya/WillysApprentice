using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;

namespace WillysApprentice;

class WikiClient
{
    private static readonly HttpClient _http = new();
    private static readonly JsonSerializerOptions _json = new() { PropertyNameCaseInsensitive = true };
    private readonly string _base;
    private readonly Dictionary<string, ItemData?> _cache = new();

    public WikiClient(int port) => _base = $"http://127.0.0.1:{port}";
    public bool IsOnline { get; private set; }

    public async Task CheckHealthAsync()
    {
        try
        {
            var r = await _http.GetAsync($"{_base}/health");
            IsOnline = r.IsSuccessStatusCode;
        }
        catch { IsOnline = false; }
    }

    public async Task<ItemData?> FetchAsync(string qualifiedId)
    {
        if (_cache.TryGetValue(qualifiedId, out var cached)) return cached;
        try
        {
            var encoded = Uri.EscapeDataString(qualifiedId);
            var resp = await _http.GetAsync($"{_base}/item/{encoded}");
            ItemData? item = null;
            if (resp.IsSuccessStatusCode)
            {
                var json = await resp.Content.ReadAsStringAsync();
                item = JsonSerializer.Deserialize<ItemData>(json, _json);
            }
            _cache[qualifiedId] = item; // cache null for 404 — data is static
            return item;
        }
        catch { return null; }
    }
}
