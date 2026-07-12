using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace WillysApprentice;

// Raw deserialization shapes — only used during DataStore construction
internal record RawItem(
    [property: JsonPropertyName("id")]          string Id,
    [property: JsonPropertyName("name")]        string Name,
    [property: JsonPropertyName("category")]    string Category,
    [property: JsonPropertyName("description")] string Description,
    [property: JsonPropertyName("sellPrice")]   int SellPrice,
    [property: JsonPropertyName("edible")]      bool Edible,
    [property: JsonPropertyName("energy")]      int Energy,
    [property: JsonPropertyName("health")]      int Health);

internal record RawIngredient(
    [property: JsonPropertyName("item")]  string Item,
    [property: JsonPropertyName("count")] int Count);

internal record RawRecipe(
    [property: JsonPropertyName("id")]          string Id,
    [property: JsonPropertyName("name")]        string Name,
    [property: JsonPropertyName("yields")]      string Yields,
    [property: JsonPropertyName("ingredients")] List<RawIngredient> Ingredients);

internal record RawBundleSlot(
    [property: JsonPropertyName("item")] string Item);

internal record RawBundle(
    [property: JsonPropertyName("id")]    string Id,
    [property: JsonPropertyName("room")]  string Room,
    [property: JsonPropertyName("name")]  string Name,
    [property: JsonPropertyName("items")] List<RawBundleSlot> Items);

class DataStore
{
    private static readonly JsonSerializerOptions _json = new() { PropertyNameCaseInsensitive = true };
    private readonly Dictionary<string, ItemData> _index = new();

    public int Count => _index.Count;

    public DataStore(string dataDir)
    {
        var items   = Read<Dictionary<string, RawItem>>(dataDir, "items.json");
        var recipes = Read<List<RawRecipe>>(dataDir, "recipes.json");
        var bundles = Read<List<RawBundle>>(dataDir, "bundles.json");
        var gifts   = Read<Dictionary<string, GiftData>>(dataDir, "gifts.json");

        // Mirrors data_layer.py: usedIn and craftedFrom built from recipes
        var usedIn      = new Dictionary<string, List<RecipeRef>>();
        var craftedFrom = new Dictionary<string, List<IngredientRef>>();
        foreach (var r in recipes)
        {
            var recipeRef = new RecipeRef(r.Id, r.Name, r.Yields);
            foreach (var ing in r.Ingredients)
            {
                if (!usedIn.TryGetValue(ing.Item, out var bucket))
                    usedIn[ing.Item] = bucket = new List<RecipeRef>();
                bucket.Add(recipeRef);
            }
            craftedFrom[r.Yields] = r.Ingredients
                .Select(ing => new IngredientRef(
                    items.TryGetValue(ing.Item, out var it) ? it.Name : ing.Item,
                    ing.Count))
                .ToList();
        }

        // Mirrors data_layer.py: inBundles built from bundles
        var inBundles = new Dictionary<string, List<BundleRef>>();
        foreach (var b in bundles)
        {
            var bundleRef = new BundleRef(b.Id, b.Room, b.Name);
            foreach (var slot in b.Items)
            {
                if (!inBundles.TryGetValue(slot.Item, out var bucket))
                    inBundles[slot.Item] = bucket = new List<BundleRef>();
                bucket.Add(bundleRef);
            }
        }

        var emptyGift = new GiftData(
            new List<string>(), new List<string>(), new List<string>(),
            new List<string>(), new List<string>());

        foreach (var (id, raw) in items)
        {
            _index[id] = new ItemData(
                raw.Id, raw.Name, raw.Category, raw.Description,
                raw.SellPrice, raw.Edible, raw.Energy, raw.Health,
                craftedFrom.TryGetValue(id, out var cf) ? cf : new List<IngredientRef>(),
                usedIn.TryGetValue(id, out var ui)      ? ui : new List<RecipeRef>(),
                inBundles.TryGetValue(id, out var ib)   ? ib : new List<BundleRef>(),
                gifts.TryGetValue(id, out var g)         ? g  : emptyGift);
        }
    }

    public ItemData? Get(string qualifiedId) =>
        _index.TryGetValue(qualifiedId, out var item) ? item : null;

    private static T Read<T>(string dir, string file) =>
        JsonSerializer.Deserialize<T>(File.ReadAllText(Path.Combine(dir, file)), _json)!;
}
