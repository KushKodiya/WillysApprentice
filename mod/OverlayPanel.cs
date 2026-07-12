using System.Collections.Generic;
using System.Linq;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using StardewValley;
using StardewValley.Menus;

namespace WillysApprentice;

class OverlayPanel
{
    private bool _visible;
    private List<string> _lines = new();
    private const int Width = 340;
    private const int LineHeight = 24;
    private const int Pad = 16;

    public bool IsVisible => _visible;

    public void ShowItem(ItemData? item)
    {
        _visible = true;
        _lines = BuildLines(item);
    }

    public void Clear()
    {
        _visible = false;
        _lines = new();
    }

    public void Draw(SpriteBatch b)
    {
        if (!_visible || _lines.Count == 0) return;

        int innerWidth = Width - Pad * 2;
        var display = WrapLines(innerWidth);

        int height = display.Count * LineHeight + Pad * 2;
        int x = 8;
        int y = Game1.viewport.Height - height - 8;

        IClickableMenu.drawTextureBox(b, x, y, Width, height, Color.White);

        for (int i = 0; i < display.Count; i++)
            b.DrawString(
                Game1.smallFont,
                display[i],
                new Vector2(x + Pad, y + Pad + i * LineHeight),
                Game1.textColor);
    }

    private List<string> WrapLines(int innerWidth)
    {
        var result = new List<string>();
        foreach (var line in _lines)
        {
            if (Game1.smallFont.MeasureString(line).X <= innerWidth)
            {
                result.Add(line);
                continue;
            }
            string current = "";
            foreach (var word in line.Split(' '))
            {
                string candidate = current.Length == 0 ? word : current + " " + word;
                if (Game1.smallFont.MeasureString(candidate).X <= innerWidth)
                    current = candidate;
                else
                {
                    if (current.Length > 0) result.Add(current);
                    current = word;
                }
            }
            if (current.Length > 0) result.Add(current);
        }
        return result;
    }

    private static List<string> BuildLines(ItemData? item)
    {
        if (item == null) return new List<string> { "No wiki data for this item." };

        var lines = new List<string>
        {
            item.Name,
            $"{item.Category}  ·  Sell: {item.SellPrice}g",
        };

        if (item.CraftedFrom.Count > 0)
            lines.Add("Craft: " + string.Join(", ", item.CraftedFrom.Select(i => $"{i.Name} x{i.Count}")));

        if (item.CraftingUses.Count > 0)
            lines.Add("Used in: " + string.Join(", ", item.CraftingUses.Select(r => r.Name)));

        if (item.Bundles.Count > 0)
            lines.Add("Bundle: " + string.Join(", ", item.Bundles.Select(b => b.Name)));

        if (item.Gifts.Loves.Count > 0)
            lines.Add("Loves: " + string.Join(", ", item.Gifts.Loves));

        if (item.Gifts.Likes.Count > 0)
            lines.Add("Likes: " + string.Join(", ", item.Gifts.Likes));

        return lines;
    }
}
