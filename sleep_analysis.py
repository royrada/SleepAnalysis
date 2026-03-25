import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta, time

# 1. Data Ingestion & Cleaning
raw = pd.read_csv('AllRawData.csv')

# --- Split into three DataFrames ---
# Sleep log: columns A-K (first 11 columns)
sleep_cols = raw.columns[:11]
sleep_log = raw[sleep_cols].copy()

# Activity: columns L-N (12-14), rows 1-80 (index 0-79)
activity_cols = raw.columns[11:14]
activity = raw.loc[:79, activity_cols].copy()

# Vitals: columns P-Y (16-24), rows 1-80 (index 0-79)
vitals_cols = raw.columns[15:24]
vitals = raw.loc[:79, vitals_cols].copy()

# --- Normalize column names ---
sleep_log.columns = [c.strip().replace(' ', '_').replace('(', '').replace(')', '').replace('%','pct').replace('.', '').replace('-', '_') for c in sleep_log.columns]
activity.columns = [c.strip().replace(' ', '_').replace('(', '').replace(')', '').replace('.', '').replace('-', '_') for c in activity.columns]
vitals.columns = [c.strip().replace(' ', '_').replace('(', '').replace(')', '').replace('.', '').replace('-', '_') for c in vitals.columns]

# --- Parse times and handle missing values ---
def parse_time(x):
    try:
        return pd.to_datetime(x)
    except:
        return pd.NaT

sleep_log['Start_Time'] = sleep_log['Start_Time'].apply(parse_time)
sleep_log['End_Time'] = sleep_log['End_Time'].apply(parse_time)
sleep_log['Falling_Asleep_Time'] = sleep_log['Falling_Asleep_Time'].apply(parse_time)
sleep_log['Wake_up_time'] = sleep_log['Wake_up_time'].apply(parse_time)

# For short naps (missing stages), mark as 'Unclassified' (np.nan)
stage_cols = [
    'Sleep_Stages___Awakemin',
    'Sleep_Stages___REMmin',
    'Sleep_Stages___Light_Sleepmin',
    'Sleep_Stages___Deep_Sleepmin'
]
for col in stage_cols:
    if col in sleep_log.columns:
        sleep_log[col] = pd.to_numeric(sleep_log[col], errors='coerce')

# 2. Sleep Day Assignment (noon-to-noon)
def assign_sleep_day(row):
    st = row['Start_Time']
    if pd.isnull(st):
        return np.nan
    noon = datetime.combine(st.date(), time(12,0))
    if st >= noon:
        return st.date()
    else:
        return (st.date() - timedelta(days=1))

sleep_log['Sleep_Day'] = sleep_log.apply(assign_sleep_day, axis=1)

# 3. Data Merging
# Activity and vitals: ensure Date columns are datetime.date
def parse_date(x):
    try:
        return pd.to_datetime(x).date()
    except:
        return np.nan

activity['Date'] = activity['Date'].apply(parse_date)
vitals['Date1'] = vitals['Date1'].apply(parse_date)

# Merge activity and vitals on Date
merge_on = 'Date_1' if 'Date_1' in vitals.columns else 'Date'
daydata = pd.merge(activity, vitals, left_on='Date', right_on='Date1', how='outer')

# Merge sleep_log with daydata on Sleep_Day/Date
sleep_log = pd.merge(sleep_log, daydata, left_on='Sleep_Day', right_on='Date', how='left', suffixes=('', '_day'))

# 4. Analysis A: REM Efficiency
long_sleeps = sleep_log[sleep_log['Time_Asleepmin'] > 120].copy()
long_sleeps = long_sleeps[~long_sleeps['Sleep_Stages___REMmin'].isna()]
long_sleeps['REM_Ratio'] = long_sleeps['Sleep_Stages___REMmin'] / long_sleeps['Time_Asleepmin']

plt.figure(figsize=(8,6))
sns.scatterplot(x='Time_Asleepmin', y='REM_Ratio', data=long_sleeps)
plt.title('REM Efficiency vs. Sleep Duration')
plt.xlabel('Total Asleep Minutes')
plt.ylabel('REM/Asleep-Minutes Ratio')
plt.tight_layout()
plt.savefig('rem_efficiency_scatter.png')
plt.close()

# 5. Analysis B: Nap Effect
def is_nap(row):
    return row['Time_Asleepmin'] < 120
sleep_log['Is_Nap'] = sleep_log.apply(is_nap, axis=1)

# Count naps per day
naps_per_day = sleep_log.groupby('Sleep_Day')['Is_Nap'].sum().reset_index(name='Num_Naps')

# For each day, get main sleep (longest sleep)
main_sleep = sleep_log.groupby('Sleep_Day').apply(lambda df: df.loc[df['Time_Asleepmin'].idxmax()])
main_sleep = main_sleep.reset_index().rename(columns={'level_1': 'orig_index'})
main_sleep = pd.merge(main_sleep, naps_per_day, on='Sleep_Day', how='left')
main_sleep['Sleep_Latency'] = (main_sleep['Falling_Asleep_Time'] - main_sleep['Start_Time']).dt.total_seconds() / 60

plt.figure(figsize=(8,6))
sns.boxplot(x=(main_sleep['Num_Naps']>0), y=main_sleep['Sleep_Latency'])
plt.title('Sleep Latency: Days With vs. Without Naps')
plt.xlabel('Had Daytime Nap(s)')
plt.ylabel('Sleep Latency (min)')
plt.tight_layout()
plt.savefig('nap_effect_latency.png')
plt.close()

# 6. Analysis C: HRV-Fragmentation
fragments_per_day = sleep_log.groupby('Sleep_Day').size().reset_index(name='Num_Fragments')
hrv_frag = pd.merge(daydata, fragments_per_day, left_on='Date', right_on='Sleep_Day', how='left')

plt.figure(figsize=(8,6))
sns.regplot(x='Avg_HRVms', y='Num_Fragments', data=hrv_frag)
plt.title('HRV vs. Sleep Fragmentation')
plt.xlabel('Average HRV (ms)')
plt.ylabel('Number of Sleep Fragments')
plt.tight_layout()
plt.savefig('hrv_fragmentation.png')
plt.close()

# 7. Visualization: 24-Hour Clock Heatmap
sleep_log['Start_Hour'] = sleep_log['Start_Time'].dt.hour + sleep_log['Start_Time'].dt.minute/60
plt.figure(figsize=(10,2))
sns.histplot(sleep_log['Start_Hour'].dropna(), bins=24, kde=False)
plt.title('Distribution of Sleep Fragment Start Times (24h)')
plt.xlabel('Hour of Day')
plt.ylabel('Number of Fragments')
plt.tight_layout()
plt.savefig('sleep_fragment_24h.png')
plt.close()

print('Analysis complete. Plots saved: rem_efficiency_scatter.png, nap_effect_latency.png, hrv_fragmentation.png, sleep_fragment_24h.png')

# --- Statistical Analysis and Text Output ---
import scipy.stats as stats
with open('analysis_results.txt', 'w') as f:
    f.write('Sleep Analysis Statistical Results\n')
    f.write('=================================\n\n')
    # 1. REM Efficiency vs. Sleep Duration
    if not long_sleeps.empty:
        slope, intercept, r_value, p_value, std_err = stats.linregress(long_sleeps['Time_Asleepmin'], long_sleeps['REM_Ratio'])
        f.write('1. REM Efficiency vs. Sleep Duration\n')
        f.write(f"  Slope: {slope:.4f}\n  Correlation (r): {r_value:.3f}\n  p-value: {p_value:.3f}\n")
        if p_value < 0.05:
            if slope > 0:
                f.write('  Conclusion: Longer sleeps are associated with higher REM fraction (statistically significant).\n')
            else:
                f.write('  Conclusion: Longer sleeps are associated with lower REM fraction (statistically significant).\n')
        else:
            f.write('  Conclusion: No statistically significant relationship between sleep duration and REM fraction.\n')
        f.write('\n')
    else:
        f.write('1. REM Efficiency vs. Sleep Duration\n  Not enough data for analysis.\n\n')

    # 2. Nap Effect on Sleep Latency
    if 'Num_Naps' in main_sleep.columns and 'Sleep_Latency' in main_sleep.columns:
        latency_nap = main_sleep[main_sleep['Num_Naps'] > 0]['Sleep_Latency'].dropna()
        latency_no_nap = main_sleep[main_sleep['Num_Naps'] == 0]['Sleep_Latency'].dropna()
        if not latency_nap.empty and not latency_no_nap.empty:
            t_stat, p_nap = stats.ttest_ind(latency_nap, latency_no_nap, equal_var=False)
            f.write('2. Nap Effect on Sleep Latency\n')
            f.write(f"  Mean latency with nap: {latency_nap.mean():.1f} min\n  Mean latency without nap: {latency_no_nap.mean():.1f} min\n  p-value: {p_nap:.3f}\n")
            if p_nap < 0.05:
                f.write('  Conclusion: Naps have a statistically significant effect on sleep latency.\n')
            else:
                f.write('  Conclusion: No statistically significant effect of naps on sleep latency.\n')
            f.write('\n')
        else:
            f.write('2. Nap Effect on Sleep Latency\n  Not enough data for analysis.\n\n')
    else:
        f.write('2. Nap Effect on Sleep Latency\n  Not enough data for analysis.\n\n')

    # 3. HRV vs. Sleep Fragmentation
    if 'Avg_HRVms' in hrv_frag.columns and 'Num_Fragments' in hrv_frag.columns:
        hrv_frag_valid = hrv_frag.dropna(subset=['Avg_HRVms', 'Num_Fragments'])
        if not hrv_frag_valid.empty:
            slope2, intercept2, r_value2, p_value2, std_err2 = stats.linregress(hrv_frag_valid['Avg_HRVms'], hrv_frag_valid['Num_Fragments'])
            f.write('3. HRV vs. Sleep Fragmentation\n')
            f.write(f"  Slope: {slope2:.4f}\n  Correlation (r): {r_value2:.3f}\n  p-value: {p_value2:.3f}\n")
            if p_value2 < 0.05:
                if slope2 < 0:
                    f.write('  Conclusion: Lower HRV is associated with more fragmented sleep (statistically significant).\n')
                else:
                    f.write('  Conclusion: Higher HRV is associated with more fragmented sleep (statistically significant).\n')
            else:
                f.write('  Conclusion: No statistically significant relationship between HRV and sleep fragmentation.\n')
            f.write('\n')
        else:
            f.write('3. HRV vs. Sleep Fragmentation\n  Not enough data for analysis.\n\n')
    else:
        f.write('3. HRV vs. Sleep Fragmentation\n  Not enough data for analysis.\n\n')
    f.write('End of analysis.\n')
