from config import FACT_DEFINITIONS

def calculate_interest(stat_type, value):
    if stat_type not in FACT_DEFINITIONS: return 0
    meta = FACT_DEFINITIONS[stat_type]
    if stat_type == 'stormtrooper':
        if value < 1.0 or value > meta['normal']: return 0
        return (meta['normal'] / value) * meta['weight']
    if value <= meta['normal']: return 0
    return (value / meta['normal']) * meta['weight']

def calculate_highlights_and_summary(data):
    candidates, summary_list = [], []
    rank = "?"
    for p in data['participants']:
        s = p['stats']
        t = data['trackers'][p['name']]
        rank = s.get('winPlace', rank)
        summary_list.append({'name': p['name'], 'kills': s.get('kills',0), 'dmg': int(s.get('damageDealt',0))})
        acc = (t['shots_hit'] / t['shots_fired'] * 100) if t['shots_fired'] > 5 else 0
        leg_pct = (t['leg_hits'] / t['shots_hit'] * 100) if t['shots_hit'] > 0 else 0
        
        data_points = {
            'medic': s.get('revives', 0), 'sniper': s.get('longestKill', 0), 'driver': s.get('rideDistance', 0),
            'swimmer': s.get('swimDistance', 0), 'brain_surgeon': s.get('headshotKills', 0),
            'blue_magnet': t['blue_magnet'], 'grenadier': t['grenadier'], 'undying': t['undying'],
            'grave_robber': t['grave_robber'], 'door_dasher': t['door_dasher'], 'hoarder': t['hoarder'],
            'traitor': t['traitor_dmg'], 'masochist': t['masochist_dmg'],
            'sponge': t['sponge_dmg'], 'junkie': t['junkie_boosts'],
            'boxer': t['boxer_dmg'], 'vandal': t['vandal_tires'], 'bot_food': 1 if t['killed_by_bot'] else 0,
            'stormtrooper': acc, 'kneecapper': leg_pct
        }
        
        if t['hoarder'] > 30 and s.get('damageDealt', 0) < 10: 
            candidates.append({'player': p['name'], 'type': 'pinata', 'value': t['hoarder'], 'score': 10})
            
        for k, v in data_points.items():
            score = calculate_interest(k, v)
            if score > 0.5: 
                candidates.append({'player': p['name'], 'type': k, 'value': v, 'score': score})
                
    candidates.sort(key=lambda x: x['score'], reverse=True)
    unique_highlights, used = [], set()
    for c in candidates:
        if len(unique_highlights) >= 8: break
        if c['type'] not in used:
            unique_highlights.append(c)
            used.add(c['type'])
            
    return summary_list, unique_highlights, rank