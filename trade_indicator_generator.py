#!/usr/bin/env python3
"""
Trade Indicator Generator
Reads a CSV file of trades and generates a Pine Script indicator to plot them on TradingView.
"""

import pandas as pd
import argparse
import sys
from datetime import datetime
from collections import defaultdict

def parse_time(time_str):
    """Parse time string and return hour, minute, second"""
    try:
        time_obj = datetime.strptime(time_str, "%H:%M:%S")
        return time_obj.hour, time_obj.minute, time_obj.second
    except ValueError:
        # Try alternative format
        try:
            time_obj = datetime.strptime(time_str, "%H:%M")
            return time_obj.hour, time_obj.minute, 0
        except ValueError:
            print(f"Warning: Could not parse time '{time_str}', skipping...")
            return None, None, None

def consolidate_trades(trades_df, symbol):
    """Consolidate trades by timestamp and price for cleaner display"""
    symbol_trades = trades_df[trades_df['Symbol'] == symbol].copy()
    
    # Group by time, side, and price
    consolidated = []
    grouped = symbol_trades.groupby(['Time', 'Side', 'Price'])
    
    for (time, side, price), group in grouped:
        total_qty = group['Qty'].sum()
        consolidated.append({
            'Time': time,
            'Side': side,
            'Price': price,
            'Qty': total_qty
        })
    
    return pd.DataFrame(consolidated)

def generate_pinescript(trades_df, symbol, output_file=None):
    """Generate Pine Script code from trades DataFrame"""
    
    # Filter trades for the specified symbol
    symbol_trades = consolidate_trades(trades_df, symbol)
    
    if symbol_trades.empty:
        print(f"No trades found for symbol {symbol}")
        return None
    
    # Separate trades by type
    buy_trades = symbol_trades[symbol_trades['Side'] == 'B'].reset_index(drop=True)
    sell_trades = symbol_trades[symbol_trades['Side'] == 'S'].reset_index(drop=True)
    short_trades = symbol_trades[symbol_trades['Side'] == 'SS'].reset_index(drop=True)
    
    # Start building the Pine Script
    script_lines = []
    
    # Header
    script_lines.extend([
        "//@version=5",
        f'indicator("{symbol} Trades Plotter", shorttitle="{symbol} Trades", overlay=true)',
        "",
        "// Input options",
        'show_buy_trades = input.bool(true, "Show Buy Trades")',
        'show_sell_trades = input.bool(true, "Show Sell Trades")',
        'show_short_trades = input.bool(true, "Show Short Sell Trades")',
        'show_labels = input.bool(true, "Show Trade Labels")',
        "",
        "// Colors for different trade types",
        "buy_color = color.new(color.green, 0)",
        "sell_color = color.new(color.red, 0)",
        "short_color = color.new(color.orange, 0)",
        "",
        "// Function to check if current bar matches trade time (exact)",
        f"// Check hour, minute, and second for precise matching, AND symbol is {symbol}",
        "is_trade_time(hour_val, minute_val, second_val) =>",
        f'    syminfo.ticker == "{symbol}" and hour(time) == hour_val and minute(time) == minute_val and second(time) == second_val',
        "",
        "// Check if we're on the correct symbol",
        f'is_{symbol.lower()}_symbol = syminfo.ticker == "{symbol}"',
        "",
        f"// {symbol} Trade Data with exact time matching (hour, minute, second)"
    ])
    
    # Generate buy trades
    if not buy_trades.empty:
        script_lines.append("// Buy trades")
        for i, trade in buy_trades.iterrows():
            hour, minute, second = parse_time(trade['Time'])
            if hour is not None:
                script_lines.append(f"buy_trade_{i+1} = is_trade_time({hour}, {minute}, {second}) ? {trade['Price']} : na    // {trade['Time']},{symbol},B,{trade['Price']},{trade['Qty']}")
    
    script_lines.append("")
    
    # Generate sell trades
    if not sell_trades.empty:
        script_lines.append("// Sell trades")
        for i, trade in sell_trades.iterrows():
            hour, minute, second = parse_time(trade['Time'])
            if hour is not None:
                script_lines.append(f"sell_trade_{i+1} = is_trade_time({hour}, {minute}, {second}) ? {trade['Price']} : na     // {trade['Time']},{symbol},S,{trade['Price']},{trade['Qty']}")
    
    script_lines.append("")
    
    # Generate short trades
    if not short_trades.empty:
        script_lines.append("// Short Sell trades")
        for i, trade in short_trades.iterrows():
            hour, minute, second = parse_time(trade['Time'])
            if hour is not None:
                script_lines.append(f"short_trade_{i+1} = is_trade_time({hour}, {minute}, {second}) ? {trade['Price']} : na    // {trade['Time']},{symbol},SS,{trade['Price']},{trade['Qty']}")
    
    script_lines.append("")
    
    # Generate plotshape calls for buy trades
    if not buy_trades.empty:
        script_lines.append("// Plot Buy trades")
        for i, trade in buy_trades.iterrows():
            script_lines.append(f'plotshape(show_buy_trades ? buy_trade_{i+1} : na, style=shape.triangleup, location=location.absolute, color=buy_color, size=size.small, title="Buy {trade["Price"]}")')
    
    script_lines.append("")
    
    # Generate plotshape calls for sell trades
    if not sell_trades.empty:
        script_lines.append("// Plot Sell trades")
        for i, trade in sell_trades.iterrows():
            script_lines.append(f'plotshape(show_sell_trades ? sell_trade_{i+1} : na, style=shape.triangledown, location=location.absolute, color=sell_color, size=size.small, title="Sell {trade["Price"]}")')
    
    script_lines.append("")
    
    # Generate plotshape calls for short trades
    if not short_trades.empty:
        script_lines.append("// Plot Short Sell trades")
        for i, trade in short_trades.iterrows():
            script_lines.append(f'plotshape(show_short_trades ? short_trade_{i+1} : na, style=shape.diamond, location=location.absolute, color=short_color, size=size.small, title="Short {trade["Price"]}")')
    
    script_lines.append("")
    
    # Generate labels
    script_lines.extend([
        "// Add labels for trade details",
        "if show_labels"
    ])
    
    # Buy trade labels
    if not buy_trades.empty:
        script_lines.append("    // Buy trade labels")
        for i, trade in buy_trades.iterrows():
            hour, minute, second = parse_time(trade['Time'])
            if hour is not None:
                script_lines.append(f'    if show_buy_trades and is_trade_time({hour}, {minute}, {second})')
                script_lines.append(f'        label.new(bar_index, {trade["Price"]}, "B @ {trade["Price"]}\\nQty: {trade["Qty"]}\\n{trade["Time"]}", style=label.style_label_left, color=buy_color, textcolor=color.white, size=size.small)')
    
    # Sell trade labels
    if not sell_trades.empty:
        script_lines.append("    ")
        script_lines.append("    // Sell trade labels")
        for i, trade in sell_trades.iterrows():
            hour, minute, second = parse_time(trade['Time'])
            if hour is not None:
                script_lines.append(f'    if show_sell_trades and is_trade_time({hour}, {minute}, {second})')
                script_lines.append(f'        label.new(bar_index, {trade["Price"]}, "S @ {trade["Price"]}\\nQty: {trade["Qty"]}\\n{trade["Time"]}", style=label.style_label_left, color=sell_color, textcolor=color.white, size=size.small)')
    
    # Short trade labels
    if not short_trades.empty:
        script_lines.append("    ")
        script_lines.append("    // Short trade labels")
        for i, trade in short_trades.iterrows():
            hour, minute, second = parse_time(trade['Time'])
            if hour is not None:
                script_lines.append(f'    if show_short_trades and is_trade_time({hour}, {minute}, {second})')
                script_lines.append(f'        label.new(bar_index, {trade["Price"]}, "SS @ {trade["Price"]}\\nQty: {trade["Qty"]}\\n{trade["Time"]}", style=label.style_label_left, color=short_color, textcolor=color.white, size=size.small)')
    
    script_lines.append("")
    
    # Summary table and warning
    buy_count = len(buy_trades)
    sell_count = len(sell_trades)
    short_count = len(short_trades)
    total_count = buy_count + sell_count + short_count
    
    script_lines.extend([
        "// Summary table or warning message",
        "if barstate.islast",
        f"    if is_{symbol.lower()}_symbol",
        f"        // Show trade summary for {symbol}",
        "        var table summary_table = table.new(position.top_right, 2, 5, bgcolor=color.white, border_width=1)",
        "        ",
        f'        table.cell(summary_table, 0, 0, "{symbol} Trades", text_color=color.black, text_size=size.normal)',
        '        table.cell(summary_table, 1, 0, "Count", text_color=color.black, text_size=size.normal)',
        '        table.cell(summary_table, 0, 1, "Buy", text_color=color.green, text_size=size.small)',
        f'        table.cell(summary_table, 1, 1, "{buy_count}", text_color=color.black, text_size=size.small)',
        '        table.cell(summary_table, 0, 2, "Sell", text_color=color.red, text_size=size.small)',
        f'        table.cell(summary_table, 1, 2, "{sell_count}", text_color=color.black, text_size=size.small)',
        '        table.cell(summary_table, 0, 3, "Short", text_color=color.orange, text_size=size.small)',
        f'        table.cell(summary_table, 1, 3, "{short_count}", text_color=color.black, text_size=size.small)',
        '        table.cell(summary_table, 0, 4, "Total", text_color=color.black, text_size=size.small)',
        f'        table.cell(summary_table, 1, 4, "{total_count}", text_color=color.black, text_size=size.small)',
        "    else",
        "        // Show warning for wrong symbol",
        "        var table warning_table = table.new(position.top_right, 1, 3, bgcolor=color.new(color.red, 80), border_width=2)",
        "        ",
        '        table.cell(warning_table, 0, 0, "⚠️ WARNING ⚠️", text_color=color.white, text_size=size.normal)',
        '        table.cell(warning_table, 0, 1, "This indicator is designed", text_color=color.white, text_size=size.small)',
        f'        table.cell(warning_table, 0, 2, "for {symbol} symbol only!", text_color=color.white, text_size=size.small)',
        ""
    ])
    
    # Add price levels based on trade prices
    all_prices = symbol_trades['Price'].tolist()
    if all_prices:
        min_price = min(all_prices)
        max_price = max(all_prices)
        mid_price = (min_price + max_price) / 2
        
        script_lines.extend([
            "// Plot horizontal lines for key price levels",
            f'hline({mid_price:.2f}, "Key Level ${mid_price:.2f}", color=color.gray, linestyle=hline.style_dashed)',
            f'hline({min_price:.2f}, "Key Level ${min_price:.2f}", color=color.gray, linestyle=hline.style_dashed)',
            f'hline({max_price:.2f}, "Key Level ${max_price:.2f}", color=color.gray, linestyle=hline.style_dashed)',
            ""
        ])
    
    # Add alert conditions
    buy_alerts = " or ".join([f"buy_trade_{i+1}" for i in range(len(buy_trades))])
    sell_alerts = " or ".join([f"sell_trade_{i+1}" for i in range(len(sell_trades))])
    short_alerts = " or ".join([f"short_trade_{i+1}" for i in range(len(short_trades))])
    
    script_lines.append("// Add alert conditions for trades")
    if buy_alerts:
        script_lines.append(f'alertcondition({buy_alerts}, title="{symbol} Buy Trade", message="{symbol} Buy trade detected")')
    if sell_alerts:
        script_lines.append(f'alertcondition({sell_alerts}, title="{symbol} Sell Trade", message="{symbol} Sell trade detected")')
    if short_alerts:
        script_lines.append(f'alertcondition({short_alerts}, title="{symbol} Short Trade", message="{symbol} Short trade detected")')
    
    script_lines.append("")
    
    # Join all lines
    script_content = "\n".join(script_lines)
    
    # Write to file
    if output_file is None:
        output_file = f"{symbol.lower()}_trades_indicator.pine"
    
    with open(output_file, 'w') as f:
        f.write(script_content)
    
    print(f"Pine Script indicator generated: {output_file}")
    print(f"Trade Summary for {symbol}:")
    print(f"  Buy trades: {buy_count}")
    print(f"  Sell trades: {sell_count}")
    print(f"  Short trades: {short_count}")
    print(f"  Total trades: {total_count}")
    
    return script_content

def main():
    parser = argparse.ArgumentParser(description='Generate Pine Script trade indicator from CSV')
    parser.add_argument('csv_file', help='Path to CSV file containing trade data')
    parser.add_argument('symbol', help='Symbol to generate indicator for (e.g., SEPN)')
    parser.add_argument('-o', '--output', help='Output Pine Script file name')
    parser.add_argument('--preview', action='store_true', help='Preview available symbols in CSV')
    
    args = parser.parse_args()
    
    try:
        # Read CSV file
        df = pd.read_csv(args.csv_file)
        
        # Check if required columns exist
        required_columns = ['Time', 'Symbol', 'Side', 'Price', 'Qty']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            print(f"Error: Missing required columns: {missing_columns}")
            print(f"Available columns: {list(df.columns)}")
            return 1
        
        # Preview mode
        if args.preview:
            print("Available symbols in CSV:")
            symbols = df['Symbol'].unique()
            for symbol in sorted(symbols):
                count = len(df[df['Symbol'] == symbol])
                print(f"  {symbol}: {count} trades")
            return 0
        
        # Generate Pine Script
        script = generate_pinescript(df, args.symbol.upper(), args.output)
        
        if script is None:
            return 1
            
        return 0
        
    except FileNotFoundError:
        print(f"Error: File '{args.csv_file}' not found")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
