using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace WillysApprentice;

record GiftData(
    [property: JsonPropertyName("loves")]    List<string> Loves,
    [property: JsonPropertyName("likes")]    List<string> Likes,
    [property: JsonPropertyName("neutrals")] List<string> Neutrals,
    [property: JsonPropertyName("dislikes")] List<string> Dislikes,
    [property: JsonPropertyName("hates")]    List<string> Hates
);

record RecipeRef(
    [property: JsonPropertyName("recipeId")] string RecipeId,
    [property: JsonPropertyName("name")]     string Name,
    [property: JsonPropertyName("yields")]   string Yields
);

record BundleRef(
    [property: JsonPropertyName("bundleId")] string BundleId,
    [property: JsonPropertyName("room")]     string Room,
    [property: JsonPropertyName("name")]     string Name
);

record ItemData(
    [property: JsonPropertyName("id")]           string Id,
    [property: JsonPropertyName("name")]         string Name,
    [property: JsonPropertyName("category")]     string Category,
    [property: JsonPropertyName("description")]  string Description,
    [property: JsonPropertyName("sellPrice")]    int SellPrice,
    [property: JsonPropertyName("edible")]       bool Edible,
    [property: JsonPropertyName("energy")]       int Energy,
    [property: JsonPropertyName("health")]       int Health,
    [property: JsonPropertyName("craftingUses")] List<RecipeRef> CraftingUses,
    [property: JsonPropertyName("bundles")]      List<BundleRef> Bundles,
    [property: JsonPropertyName("gifts")]        GiftData Gifts
);
