#!/usr/bin/env python3
"""
Trade Indicator Generator
Reads a CSV file of trades and generates a Pine Script indicator to plot them on TradingView.
Now includes timeframe awareness to match trades to the nearest time unit.
Updated to parse date from last CSV field and compare both date and timestamp for plotting trades.
Enhanced to parse dates from Cloid field when no explicit date column exists.
Fixed overlapping trade indicators by adding vertical offsets for different trade types.
"""

import pandas as pd
import argparse
import sys
from datetime import datetime, date
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

def parse_date(date_str):
    """Parse date string and return year, month, day"""
    if pd.isna(date_str) or date_str == '' or date_str is None:
        return None, None, None
    
    try:
        # Try common date formats
        date_formats = [
            "%Y-%m-%d",      # 2024-05-14
            "%m/%d/%Y",      # 05/14/2024
            "%m/%d/%y",      # 05/14/24
            "%Y%m%d",        # 20240514
            "%m-%d-%Y",      # 05-14-2024
            "%d/%m/%Y",      # 14/05/2024
        ]
        
        for fmt in date_formats:
            try:
                date_obj = datetime.strptime(str(date_str).strip(), fmt)
                return date_obj.year, date_obj.month, date_obj.day
            except ValueError:
                continue
        
        print(f"Warning: Could not parse date '{date_str}', skipping...")
        return None, None, None
    except Exception as e:
        print(f"Warning: Error parsing date '{date_str}': {e}")
        return None, None, None

def parse_date_from_cloid(cloid_str):
    """Parse date from Cloid field (format: [Letter][YY][MM][DD][sequence])
    Example: Q2505140017405 -> 2025-05-14
    """
    if pd.isna(cloid_str) or cloid_str == '' or cloid_str is None:
        return None, None, None
    
    try:
        cloid_str = str(cloid_str).strip()
        
        # Check if it matches the expected pattern: Letter + 6 digits + more digits
        if len(cloid_str) >= 7 and cloid_str[0].isalpha():
            # Extract the date part: positions 1-6 (YYMMDD)
            date_part = cloid_str[1:7]
            
            if len(date_part) == 6 and date_part.isdigit():
                year_part = date_part[0:2]  # YY
                month_part = date_part[2:4]  # MM
                day_part = date_part[4:6]    # DD
                
                # Convert 2-digit year to 4-digit year (assuming 20XX)
                year = 2000 + int(year_part)
                month = int(month_part)
                day = int(day_part)
                
                # Validate the date
                if 1 <= month <= 12 and 1 <= day <= 31:
                    return year, month, day
        
        return None, None, None
    except Exception as e:
        print(f"Warning: Error parsing date from Cloid '{cloid_str}': {e}")
        return None, None, None

def consolidate_trades(trades_df, symbol):
    """Consolidate trades by timestamp and price for cleaner display"""
    symbol_trades = trades_df[trades_df['Symbol'] == symbol].copy()
    
    # Group by time, side, price, and date (if available)
    group_cols = ['Time', 'Side', 'Price']
    if 'Date' in symbol_trades.columns:
        group_cols.append('Date')
    
    consolidated = []
    grouped = symbol_trades.groupby(group_cols)
    
    for group_key, group in grouped:
        total_qty = group['Qty'].sum()
        trade_data = {
            'Time': group_key[0],
            'Side': group_key[1],
            'Price': group_key[2],
            'Qty': total_qty
        }
        if len(group_key) > 3:  # Date is included
            trade_data['Date'] = group_key[3]
        consolidated.append(trade_data)
    
    return pd.DataFrame(consolidated)

def generate_pinescript(trades_df, symbol, output_file=None):
    """Generate Pine Script code from trades DataFrame"""
    
    # Check if there's a date column (last column)
    has_date_column = False
    date_column_name = None
    date_source = None
    
    # Get the last column that has actual data
    last_col_idx = len(trades_df.columns) - 1
    while last_col_idx >= 0:
        col_name = trades_df.columns[last_col_idx]
        if not trades_df[col_name].isna().all() and col_name not in ['Time', 'Symbol', 'Side', 'Price', 'Qty', 'Route', 'Broker', 'Account', 'Type', 'Cloid']:
            has_date_column = True
            date_column_name = col_name
            date_source = "explicit_column"
            break
        last_col_idx -= 1
    
    # If no explicit date column found, check if there's an unnamed column at the end
    if not has_date_column and len(trades_df.columns) > 10:
        # Check for unnamed columns that might contain dates
        for col in trades_df.columns:
            if col.startswith('Unnamed:') or col == '':
                if not trades_df[col].isna().all():
                    has_date_column = True
                    date_column_name = col
                    date_source = "unnamed_column"
                    break
    
    # If still no date column found, try to parse from Cloid field
    if not has_date_column and 'Cloid' in trades_df.columns:
        print("No explicit date column found, attempting to parse dates from Cloid field...")
        trades_df['Date'] = trades_df['Cloid'].apply(lambda x: parse_date_from_cloid(x))
        # Check if we successfully parsed any dates
        valid_dates = trades_df['Date'].apply(lambda x: x[0] is not None if isinstance(x, tuple) else False)
        if valid_dates.any():
            has_date_column = True
            date_column_name = "Cloid"
            date_source = "cloid_parsed"
            print(f"Successfully parsed {valid_dates.sum()} dates from Cloid field")
        else:
            print("Could not parse dates from Cloid field")
    
    # Add date parsing if date column exists
    if has_date_column and date_column_name and date_source != "cloid_parsed":
        print(f"Found date column: {date_column_name}")
        trades_df['Date'] = trades_df[date_column_name].apply(lambda x: parse_date(x))
        trades_df = trades_df[trades_df['Date'].apply(lambda x: x[0] is not None)]  # Filter out unparseable dates
    elif has_date_column and date_source == "cloid_parsed":
        # Already parsed from Cloid, just filter out unparseable dates
        trades_df = trades_df[trades_df['Date'].apply(lambda x: x[0] is not None)]
    
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
        "// Vertical offset calculation to prevent overlapping trades",
        "// Calculate dynamic offset based on price range",
        "price_range = ta.highest(high, 100) - ta.lowest(low, 100)",
        "offset_amount = price_range * 0.002  // 0.2% of price range",
        "",
    ])
    
    # Add date-aware or time-only matching function
    if has_date_column:
        script_lines.extend([
            "// Function to check if current bar matches trade date and time (date and timeframe aware)",
            f"// Check year, month, day, hour, minute, and second with timeframe tolerance, AND symbol is {symbol}",
            "is_trade_datetime(year_val, month_val, day_val, hour_val, minute_val, second_val) =>",
            f'    if syminfo.ticker != "{symbol}"',
            "        false",
            "    else",
            "        // Get timeframe in seconds",
            "        tf_seconds = timeframe.in_seconds()",
            "        ",
            "        // Check date match first",
            "        date_match = year(time) == year_val and month(time) == month_val and dayofmonth(time) == day_val",
            "        ",
            "        // Then check time with timeframe tolerance and handle overflow",
            "        rounded_sec = math.round(second_val / tf_seconds) * tf_seconds",
            "        ",
            "        // Handle second overflow (when rounded_sec >= 60)",
            "        adjusted_hour = hour_val",
            "        adjusted_minute = minute_val",
            "        adjusted_second = rounded_sec",
            "        ",
            "        if adjusted_second >= 60",
            "            adjusted_second := adjusted_second - 60",
            "            adjusted_minute := adjusted_minute + 1",
            "            ",
            "            // Handle minute overflow (when minute >= 60)",
            "            if adjusted_minute >= 60",
            "                adjusted_minute := adjusted_minute - 60",
            "                adjusted_hour := adjusted_hour + 1",
            "                ",
            "                // Handle hour overflow (when hour >= 24)",
            "                if adjusted_hour >= 24",
            "                    adjusted_hour := adjusted_hour - 24",
            "        ",
            "        time_match = hour(time) == adjusted_hour and minute(time) == adjusted_minute and second(time) == adjusted_second",
            "        ",
            "        // Both date and time must match",
            "        date_match and time_match",
            "",
        ])
    else:
        script_lines.extend([
            "// Function to check if current bar matches trade time (timeframe aware)",
            f"// Check hour, minute, and second with timeframe tolerance, AND symbol is {symbol}",
            "is_trade_time(hour_val, minute_val, second_val) =>",
            f'    if syminfo.ticker != "{symbol}"',
            "        false",
            "    else",
            "        // Get timeframe in seconds",
            "        tf_seconds = timeframe.in_seconds()",
            "        ",
            "        // Updated trade time matching with normalized seconds and handle overflow",
            "        rounded_sec = math.round(second_val / tf_seconds) * tf_seconds",
            "        ",
            "        // Handle second overflow (when rounded_sec >= 60)",
            "        adjusted_hour = hour_val",
            "        adjusted_minute = minute_val",
            "        adjusted_second = rounded_sec",
            "        ",
            "        if adjusted_second >= 60",
            "            adjusted_second := adjusted_second - 60",
            "            adjusted_minute := adjusted_minute + 1",
            "            ",
            "            // Handle minute overflow (when minute >= 60)",
            "            if adjusted_minute >= 60",
            "                adjusted_minute := adjusted_minute - 60",
            "                adjusted_hour := adjusted_hour + 1",
            "                ",
            "                // Handle hour overflow (when hour >= 24)",
            "                if adjusted_hour >= 24",
            "                    adjusted_hour := adjusted_hour - 24",
            "        ",
            "        hour(time) == adjusted_hour and minute(time) == adjusted_minute and second(time) == adjusted_second",
            "",
        ])
    
    script_lines.extend([
        "// Check if we're on the correct symbol",
        f'is_{symbol.lower()}_symbol = syminfo.ticker == "{symbol}"',
        "",
        f"// {symbol} Trade Data with {'date and ' if has_date_column else ''}timeframe-aware time matching"
    ])
    
    # Generate buy trades with offset
    if not buy_trades.empty:
        script_lines.append("// Buy trades (with upward offset to prevent overlap)")
        for i, trade in buy_trades.iterrows():
            hour, minute, second = parse_time(trade['Time'])
            if hour is not None:
                if has_date_column and 'Date' in trade:
                    year, month, day = trade['Date'] if isinstance(trade['Date'], tuple) else (None, None, None)
                    if year is not None:
                        script_lines.append(f"buy_trade_{i+1} = is_trade_datetime({year}, {month}, {day}, {hour}, {minute}, {second}) ? {trade['Price']} + offset_amount : na    // {year}-{month:02d}-{day:02d},{trade['Time']},{symbol},B,{trade['Price']},{trade['Qty']}")
                    else:
                        script_lines.append(f"buy_trade_{i+1} = is_trade_time({hour}, {minute}, {second}) ? {trade['Price']} + offset_amount : na    // {trade['Time']},{symbol},B,{trade['Price']},{trade['Qty']}")
                else:
                    script_lines.append(f"buy_trade_{i+1} = is_trade_time({hour}, {minute}, {second}) ? {trade['Price']} + offset_amount : na    // {trade['Time']},{symbol},B,{trade['Price']},{trade['Qty']}")
    
    script_lines.append("")
    
    # Generate sell trades (no offset - baseline)
    if not sell_trades.empty:
        script_lines.append("// Sell trades (baseline - no offset)")
        for i, trade in sell_trades.iterrows():
            hour, minute, second = parse_time(trade['Time'])
            if hour is not None:
                if has_date_column and 'Date' in trade:
                    year, month, day = trade['Date'] if isinstance(trade['Date'], tuple) else (None, None, None)
                    if year is not None:
                        script_lines.append(f"sell_trade_{i+1} = is_trade_datetime({year}, {month}, {day}, {hour}, {minute}, {second}) ? {trade['Price']} : na     // {year}-{month:02d}-{day:02d},{trade['Time']},{symbol},S,{trade['Price']},{trade['Qty']}")
                    else:
                        script_lines.append(f"sell_trade_{i+1} = is_trade_time({hour}, {minute}, {second}) ? {trade['Price']} : na     // {trade['Time']},{symbol},S,{trade['Price']},{trade['Qty']}")
                else:
                    script_lines.append(f"sell_trade_{i+1} = is_trade_time({hour}, {minute}, {second}) ? {trade['Price']} : na     // {trade['Time']},{symbol},S,{trade['Price']},{trade['Qty']}")
    
    script_lines.append("")
    
    # Generate short trades with downward offset
    if not short_trades.empty:
        script_lines.append("// Short Sell trades (with downward offset to prevent overlap)")
        for i, trade in short_trades.iterrows():
            hour, minute, second = parse_time(trade['Time'])
            if hour is not None:
                if has_date_column and 'Date' in trade:
                    year, month, day = trade['Date'] if isinstance(trade['Date'], tuple) else (None, None, None)
                    if year is not None:
                        script_lines.append(f"short_trade_{i+1} = is_trade_datetime({year}, {month}, {day}, {hour}, {minute}, {second}) ? {trade['Price']} - offset_amount : na    // {year}-{month:02d}-{day:02d},{trade['Time']},{symbol},SS,{trade['Price']},{trade['Qty']}")
                    else:
                        script_lines.append(f"short_trade_{i+1} = is_trade_time({hour}, {minute}, {second}) ? {trade['Price']} - offset_amount : na    // {trade['Time']},{symbol},SS,{trade['Price']},{trade['Qty']}")
                else:
                    script_lines.append(f"short_trade_{i+1} = is_trade_time({hour}, {minute}, {second}) ? {trade['Price']} - offset_amount : na    // {trade['Time']},{symbol},SS,{trade['Price']},{trade['Qty']}")
    
    script_lines.append("")
    
    # Generate plotshape calls for buy trades
    if not buy_trades.empty:
        script_lines.append("// Plot Buy trades (green triangles above price)")
        for i, trade in buy_trades.iterrows():
            script_lines.append(f'plotshape(show_buy_trades ? buy_trade_{i+1} : na, style=shape.triangleup, location=location.absolute, color=buy_color, size=size.small, title="Buy {trade["Price"]}")')
    
    script_lines.append("")
    
    # Generate plotshape calls for sell trades
    if not sell_trades.empty:
        script_lines.append("// Plot Sell trades (red triangles at exact price)")
        for i, trade in sell_trades.iterrows():
            script_lines.append(f'plotshape(show_sell_trades ? sell_trade_{i+1} : na, style=shape.triangledown, location=location.absolute, color=sell_color, size=size.small, title="Sell {trade["Price"]}")')
    
    script_lines.append("")
    
    # Generate plotshape calls for short trades
    if not short_trades.empty:
        script_lines.append("// Plot Short Sell trades (orange diamonds below price)")
        for i, trade in short_trades.iterrows():
            script_lines.append(f'plotshape(show_short_trades ? short_trade_{i+1} : na, style=shape.diamond, location=location.absolute, color=short_color, size=size.small, title="Short {trade["Price"]}")')
    
    script_lines.append("")
    
    # Generate labels with offset-aware positioning
    script_lines.extend([
        "// Add labels for trade details (positioned at actual trade price, not offset)",
        "if show_labels"
    ])
    
    # Buy trade labels (positioned at actual price, not offset)
    if not buy_trades.empty:
        script_lines.append("    // Buy trade labels")
        for i, trade in buy_trades.iterrows():
            hour, minute, second = parse_time(trade['Time'])
            if hour is not None:
                if has_date_column and 'Date' in trade:
                    year, month, day = trade['Date'] if isinstance(trade['Date'], tuple) else (None, None, None)
                    if year is not None:
                        script_lines.append(f'    if show_buy_trades and is_trade_datetime({year}, {month}, {day}, {hour}, {minute}, {second})')
                        script_lines.append(f'        label.new(bar_index, {trade["Price"]} + offset_amount * 1.5, "B @ {trade["Price"]}\\nQty: {trade["Qty"]}\\n{year}-{month:02d}-{day:02d} {trade["Time"]}", style=label.style_label_down, color=buy_color, textcolor=color.white, size=size.small)')
                    else:
                        script_lines.append(f'    if show_buy_trades and is_trade_time({hour}, {minute}, {second})')
                        script_lines.append(f'        label.new(bar_index, {trade["Price"]} + offset_amount * 1.5, "B @ {trade["Price"]}\\nQty: {trade["Qty"]}\\n{trade["Time"]}", style=label.style_label_down, color=buy_color, textcolor=color.white, size=size.small)')
                else:
                    script_lines.append(f'    if show_buy_trades and is_trade_time({hour}, {minute}, {second})')
                    script_lines.append(f'        label.new(bar_index, {trade["Price"]} + offset_amount * 1.5, "B @ {trade["Price"]}\\nQty: {trade["Qty"]}\\n{trade["Time"]}", style=label.style_label_down, color=buy_color, textcolor=color.white, size=size.small)')
    
    # Sell trade labels
    if not sell_trades.empty:
        script_lines.append("    ")
        script_lines.append("    // Sell trade labels")
        for i, trade in sell_trades.iterrows():
            hour, minute, second = parse_time(trade['Time'])
            if hour is not None:
                if has_date_column and 'Date' in trade:
                    year, month, day = trade['Date'] if isinstance(trade['Date'], tuple) else (None, None, None)
                    if year is not None:
                        script_lines.append(f'    if show_sell_trades and is_trade_datetime({year}, {month}, {day}, {hour}, {minute}, {second})')
                        script_lines.append(f'        label.new(bar_index, {trade["Price"]}, "S @ {trade["Price"]}\\nQty: {trade["Qty"]}\\n{year}-{month:02d}-{day:02d} {trade["Time"]}", style=label.style_label_left, color=sell_color, textcolor=color.white, size=size.small)')
                    else:
                        script_lines.append(f'    if show_sell_trades and is_trade_time({hour}, {minute}, {second})')
                        script_lines.append(f'        label.new(bar_index, {trade["Price"]}, "S @ {trade["Price"]}\\nQty: {trade["Qty"]}\\n{trade["Time"]}", style=label.style_label_left, color=sell_color, textcolor=color.white, size=size.small)')
                else:
                    script_lines.append(f'    if show_sell_trades and is_trade_time({hour}, {minute}, {second})')
                    script_lines.append(f'        label.new(bar_index, {trade["Price"]}, "S @ {trade["Price"]}\\nQty: {trade["Qty"]}\\n{trade["Time"]}", style=label.style_label_left, color=sell_color, textcolor=color.white, size=size.small)')
    
    # Short trade labels
    if not short_trades.empty:
        script_lines.append("    ")
        script_lines.append("    // Short trade labels")
        for i, trade in short_trades.iterrows():
            hour, minute, second = parse_time(trade['Time'])
            if hour is not None:
                if has_date_column and 'Date' in trade:
                    year, month, day = trade['Date'] if isinstance(trade['Date'], tuple) else (None, None, None)
                    if year is not None:
                        script_lines.append(f'    if show_short_trades and is_trade_datetime({year}, {month}, {day}, {hour}, {minute}, {second})')
                        script_lines.append(f'        label.new(bar_index, {trade["Price"]} - offset_amount * 1.5, "SS @ {trade["Price"]}\\nQty: {trade["Qty"]}\\n{year}-{month:02d}-{day:02d} {trade["Time"]}", style=label.style_label_up, color=short_color, textcolor=color.white, size=size.small)')
                    else:
                        script_lines.append(f'    if show_short_trades and is_trade_time({hour}, {minute}, {second})')
                        script_lines.append(f'        label.new(bar_index, {trade["Price"]} - offset_amount * 1.5, "SS @ {trade["Price"]}\\nQty: {trade["Qty"]}\\n{trade["Time"]}", style=label.style_label_up, color=short_color, textcolor=color.white, size=size.small)')
                else:
                    script_lines.append(f'    if show_short_trades and is_trade_time({hour}, {minute}, {second})')
                    script_lines.append(f'        label.new(bar_index, {trade["Price"]} - offset_amount * 1.5, "SS @ {trade["Price"]}\\nQty: {trade["Qty"]}\\n{trade["Time"]}", style=label.style_label_up, color=short_color, textcolor=color.white, size=size.small)')
    
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
        "        var table summary_table = table.new(position.top_right, 2, 8, bgcolor=color.white, border_width=1)",
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
        '        table.cell(summary_table, 0, 5, "Timeframe", text_color=color.blue, text_size=size.small)',
        '        table.cell(summary_table, 1, 5, timeframe.period, text_color=color.black, text_size=size.small)',
        '        table.cell(summary_table, 0, 6, "Anti-Overlap", text_color=color.purple, text_size=size.small)',
        '        table.cell(summary_table, 1, 6, "Enabled", text_color=color.black, text_size=size.small)',
    ])
    
    if has_date_column:
        date_source_text = {
            "explicit_column": "Column",
            "unnamed_column": "Unnamed",
            "cloid_parsed": "Cloid"
        }.get(date_source, "Yes")
        
        script_lines.extend([
            '        table.cell(summary_table, 0, 7, "Date Source", text_color=color.gray, text_size=size.small)',
            f'        table.cell(summary_table, 1, 7, "{date_source_text}", text_color=color.black, text_size=size.small)',
        ])
    else:
        script_lines.extend([
            '        table.cell(summary_table, 0, 7, "Date Aware", text_color=color.gray, text_size=size.small)',
            '        table.cell(summary_table, 1, 7, "No", text_color=color.black, text_size=size.small)',
        ])
    
    script_lines.extend([
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
    
    # Add timeframe information comment
    script_lines.extend([
        "// Timeframe and Date Awareness:",
        "// - For 1min+ timeframes: Trades match to nearest timeframe boundary",
        "// - For sub-minute timeframes: Trades match with tolerance",
        "// - 10s timeframe: Trades match within 10-second windows",
        "// - 5s timeframe: Trades match within 5-second windows",
        "// - Anti-overlap feature: Buy trades offset upward, Short trades offset downward",
        "// - Sell trades remain at exact price as baseline reference",
    ])
    
    if has_date_column:
        script_lines.extend([
            "// - Date matching: Trades only match on the exact date",
            "// - Both date and time must match for trade to be plotted",
            f"// - Date source: {date_source}"
        ])
    else:
        script_lines.extend([
            "// - No date column found: Using time-only matching",
            "// - WARNING: Trades from different days with same time will match"
        ])
    
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
    print(f"\nTimeframe Features:")
    print(f"  - Automatically adapts to chart timeframe")
    print(f"  - 10s charts: Matches trades within 10-second windows")
    print(f"  - 1min+ charts: Matches trades to timeframe boundaries")
    print(f"  - Shows current timeframe in summary table")
    print(f"  - Anti-overlap: Buy trades offset +0.2%, Short trades offset -0.2%")
    
    if has_date_column:
        print(f"  - Date-aware matching: Both date and time must match")
        if date_source == "cloid_parsed":
            print(f"  - Date source: Parsed from Cloid field")
        else:
            print(f"  - Date column detected: {date_column_name}")
    else:
        print(f"  - Time-only matching (no date column found)")
        print(f"  - WARNING: Trades from different days with same time will match")
    
    return script_content

def main():
    parser = argparse.ArgumentParser(description="Generate Pine Script trade indicator from CSV")
    parser.add_argument("csv_file", help="Path to CSV file containing trade data")
    parser.add_argument("symbol", nargs="?", help="Symbol to generate indicator for (e.g., SEPN)")
    parser.add_argument("-o", "--output", help="Output Pine Script file name")
    parser.add_argument("--preview", action="store_true", help="Preview available symbols in CSV")
    
    args = parser.parse_args()
    
    try:
        # Read CSV file - try without pandas first
        try:
            import pandas as pd
            df = pd.read_csv(args.csv_file)
        except ImportError:
            print("Error: pandas is required. Please install with: pip install pandas")
            return 1
        
        # Check if required columns exist
        required_columns = ["Time", "Symbol", "Side", "Price", "Qty"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            print(f"Error: Missing required columns: {missing_columns}")
            print(f"Available columns: {list(df.columns)}")
            return 1
        
        # Preview mode
        if args.preview:
            print("Available symbols in CSV:")
            symbols = df["Symbol"].unique()
            for symbol in sorted(symbols):
                count = len(df[df["Symbol"] == symbol])
                print(f"  {symbol}: {count} trades")
            
            # Show column information
            print(f"\nCSV Structure:")
            print(f"  Columns: {list(df.columns)}")
            print(f"  Total rows: {len(df)}")
            
            # Check for potential date columns
            potential_date_cols = []
            for col in df.columns:
                if col not in required_columns and not df[col].isna().all():
                    potential_date_cols.append(col)
            
            if potential_date_cols:
                print(f"  Potential date columns: {potential_date_cols}")
            
            return 0
        
        # Check if symbol was provided
        if not args.symbol:
            print("Error: Symbol is required when not using --preview")
            print("Use --preview to see available symbols")
            return 1
        
        # Generate Pine Script
        script = generate_pinescript(df, args.symbol.upper(), args.output)
        
        if script is None:
            return 1
            
        return 0
        
    except FileNotFoundError:
        print(f"Error: File \"{args.csv_file}\" not found")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
