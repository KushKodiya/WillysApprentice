using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using StardewValley;
using StardewValley.Menus;

namespace WillysApprentice;

class OverlayPanel
{
    private enum State { Hidden, Loading, Loaded }
    private State _state = State.Hidden;
    private List<string> _lines = new();
    private const int Width = 340;
    private const int LineHeight = 24;
    private const int Pad = 16;

    public bool IsVisible => _state != State.Hidden;

    public void ShowLoading(string id)
    {
        _state = State.Loading;
        _lines = new List<string> { $"Loading {id}…" };
    }

    public void ShowItem(ItemData? item)
    {
        _state = State.Loaded;
        _lines = BuildLines(item);
    }

    public void ShowOffline()
    {
        _state = State.Loaded;
        _lines = new List<string> { "Wiki offline — run: python -m src.server" };
    }

    public void Clear()
    {
        _state = State.Hidden;
        _lines = new();
    }

    public void Draw(SpriteBatch b)
    {
        if (_state == State.Hidden || _lines.Count == 0) return;

        int height = _lines.Count * LineHeight + Pad * 2;
        var cursor = Game1.getMousePosition();
        int x = Math.Min(cursor.X + 20, Game1.viewport.Width - Width - 8);
        int y = Math.Min(cursor.Y + 20, Game1.viewport.Height - height - 8);

        IClickableMenu.drawTextureBox(b, x, y, Width, height, Color.White);

        for (int i = 0; i < _lines.Count; i++)
            b.DrawString(
                Game1.smallFont,
                _lines[i],
                new Vector2(x + Pad, y + Pad + i * LineHeight),
                Game1.textColor);
    }

    private static List<string> BuildLines(ItemData? item)
    {
        if (item == null) return new List<string> { "No wiki data for this item." };

        var lines = new List<string>
        {
            item.Name,
            $"{item.Category}  ·  Sell: {item.SellPrice}g",
        };

        if (!string.IsNullOrEmpty(item.Description))
            lines.Add(item.Description.Length > 46 ? item.Description[..43] + "…" : item.Description);

        if (item.CraftingUses.Count > 0)
            lines.Add("Crafting: " + string.Join(", ", item.CraftingUses.Select(r => r.Name)));

        if (item.Bundles.Count > 0)
            lines.Add("Bundle: " + string.Join(", ", item.Bundles.Select(b => b.Name)));

        if (item.Gifts.Loves.Count > 0)
            lines.Add("Loves: " + string.Join(", ", item.Gifts.Loves));

        if (item.Gifts.Likes.Count > 0)
            lines.Add("Likes: " + string.Join(", ", item.Gifts.Likes));

        return lines;
    }
}
