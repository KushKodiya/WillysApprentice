using System.Collections.Concurrent;
using System.Threading.Tasks;
using StardewModdingAPI;
using StardewModdingAPI.Events;
using StardewValley;
using StardewValley.TerrainFeatures;

namespace WillysApprentice;

class ModConfig
{
    public SButton HotKey { get; set; } = SButton.Tab;
    public int ServerPort { get; set; } = 5310;
}

public class ModEntry : Mod
{
    private ModConfig _config = new();
    private WikiClient _client = null!;
    private IModHelper _helper = null!;
    private readonly OverlayPanel _panel = new();
    private string? _hoveredId;
    // Fetch results enqueued on background thread, drained on main thread in UpdateTicked
    private readonly ConcurrentQueue<(string Id, ItemData? Item, bool Offline)> _fetchResults = new();

    public override void Entry(IModHelper helper)
    {
        _helper = helper;
        _config = helper.ReadConfig<ModConfig>();
        _client = new WikiClient(_config.ServerPort);

        helper.Events.GameLoop.GameLaunched += OnLaunched;
        helper.Events.GameLoop.UpdateTicked += OnUpdateTicked;
        helper.Events.Input.ButtonPressed += OnButtonPressed;
        // Rendered fires last in the frame — draws on top of menus
        helper.Events.Display.Rendered += (_, e) => _panel.Draw(e.SpriteBatch);
    }

    private void OnLaunched(object? sender, GameLaunchedEventArgs e)
    {
        Task.Run(async () =>
        {
            await _client.CheckHealthAsync();
            if (!_client.IsOnline)
                Monitor.Log("Wiki server offline — overlay disabled until server starts.", LogLevel.Warn);
        });
    }

    private void OnUpdateTicked(object? sender, UpdateTickedEventArgs e)
    {
        if (!Context.IsWorldReady) return;

        // Apply fetch results on the main thread; discard if hovered item changed or panel was dismissed
        while (_fetchResults.TryDequeue(out var result))
        {
            if (_hoveredId == result.Id && _panel.IsVisible)
            {
                if (result.Offline) _panel.ShowOffline();
                else _panel.ShowItem(result.Item);
            }
        }

        var newId = GetHoveredItemId();
        if (newId == _hoveredId) return;
        _hoveredId = newId;
        if (_panel.IsVisible && newId == null)
            _panel.Clear();
    }

    private void OnButtonPressed(object? sender, ButtonPressedEventArgs e)
    {
        if (e.Button != _config.HotKey) return;
        if (!Context.IsWorldReady) return;
        _helper.Input.Suppress(e.Button); // prevent game from also acting on this key

        if (_panel.IsVisible) { _panel.Clear(); return; }
        if (_hoveredId == null) return;

        var idToFetch = _hoveredId;
        _panel.ShowLoading(idToFetch);
        Task.Run(async () =>
        {
            var (item, offline) = await _client.FetchAsync(idToFetch);
            _fetchResults.Enqueue((idToFetch, item, offline));
        });
    }

    private string? GetHoveredItemId()
    {
        if (Game1.activeClickableMenu != null)
        {
            var item = GetMenuHoveredItem(Game1.activeClickableMenu);
            if (item != null) return item.QualifiedItemId;
            return null;
        }

        if (Game1.currentLocation == null) return null;
        var tile = Game1.currentCursorTile;

        // Objects and big craftables share location.objects in SV 1.6
        if (Game1.currentLocation.objects.TryGetValue(tile, out var obj))
            return obj.QualifiedItemId;

        if (Game1.currentLocation.terrainFeatures.TryGetValue(tile, out var tf)
            && tf is HoeDirt hd && hd.crop != null)
        {
            var harvestId = hd.crop.indexOfHarvest.Value;
            // indexOfHarvest is a NetString in 1.6; may already be qualified
            return harvestId.StartsWith('(') ? harvestId : $"(O){harvestId}";
        }

        return null;
    }

    private static StardewValley.Item? GetMenuHoveredItem(StardewValley.Menus.IClickableMenu menu) => menu switch
    {
        StardewValley.Menus.GameMenu gm => GetGameMenuHoveredItem(gm),
        StardewValley.Menus.MenuWithInventory mwi => mwi.hoveredItem,
        // ISalable covers tools/objects/furniture — nearly all are Item subclasses; 'as' handles the rest
        StardewValley.Menus.ShopMenu sm => sm.hoveredItem as StardewValley.Item,
        _ => null
    };

    private static StardewValley.Item? GetGameMenuHoveredItem(StardewValley.Menus.GameMenu gm)
    {
        if (gm.currentTab != StardewValley.Menus.GameMenu.inventoryTab) return null;
        if (gm.GetCurrentPage() is StardewValley.Menus.InventoryPage ip) return ip.hoveredItem;
        return null;
    }
}
