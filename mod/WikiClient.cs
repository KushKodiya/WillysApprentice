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

    // Returns (item, offline=false) on success or 404, (null, offline=true) on connection failure.
    // 404s are cached (item absent from dump is a permanent fact); connection failures are not.
    public async Task<(ItemData? Item, bool Offline)> FetchAsync(string qualifiedId)
    {
        if (_cache.TryGetValue(qualifiedId, out var cached)) return (cached, false);
        try
        {
            var encoded = Uri.EscapeDataString(qualifiedId);
            var resp = await _http.GetAsync($"{_base}/item/{encoded}");
            if (resp.IsSuccessStatusCode)
            {
                var json = await resp.Content.ReadAsStringAsync();
                var item = JsonSerializer.Deserialize<ItemData>(json, _json);
                _cache[qualifiedId] = item;
                IsOnline = true;
                return (item, false);
            }
            // 404 or other HTTP error: server is reachable, item just not in dump
            _cache[qualifiedId] = null;
            return (null, false);
        }
        catch
        {
            // Connection-level failure: server unreachable
            IsOnline = false;
            return (null, true); // not cached — may succeed next time
        }
    }
}
