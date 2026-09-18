"""100 curated instruction presets, not 100 independent models."""
GROUPS = {
    'Writing': ['Article writer','Email composer','Copy editor','Story builder','Poetry studio','Script writer','Headline lab','Tone rewriter','Resume coach','Cover letter'],
    'Research': ['Web researcher','Source comparison','Fact checker','Topic explorer','Literature guide','Trend scout','Question builder','Research outline','Evidence review','Executive brief'],
    'Coding': ['Python assistant','JavaScript helper','SQL builder','Code reviewer','Bug detective','Test writer','API designer','Regex helper','Git guide','Architecture advisor'],
    'Learning': ['Concept explainer','Socratic tutor','Study planner','Flashcard maker','Quiz builder','Language partner','Math tutor','Science guide','History explorer','Learning roadmap'],
    'Productivity': ['Task planner','Meeting notes','Decision matrix','Goal setter','Time planner','Checklist maker','Habit coach','Project brief','Priority sorter','Weekly review'],
    'Business': ['Business planner','Market analysis','SWOT analysis','Pitch builder','Customer persona','Interview planner','Product strategy','Pricing brainstorm','Proposal writer','Risk review'],
    'Creative': ['Idea generator','World builder','Character creator','Game designer','Naming studio','Design brief','Visual prompt','Content calendar','Campaign ideas','Creative critique'],
    'Data': ['Data explainer','Statistics tutor','Spreadsheet helper','Chart advisor','JSON formatter','Schema designer','Data quality','Survey designer','Metric planner','Report writer'],
    'Everyday': ['Travel planner','Recipe ideas','Meal planner','Fitness ideas','Mindful reflection','Budget planner','Gift finder','Event planner','DIY guide','Voice assistant'],
    'Knowledge': ['Document summary','Key takeaways','Knowledge organizer','Glossary builder','FAQ generator','Compare concepts','Analogy maker','Step by step guide','Translation helper','Critical thinking'],
}


def _make_prompt(name):
    if name == 'Voice assistant':
        return (
            'Act as a responsive, conversational voice assistant. Keep answers natural, direct, '
            'and tailored for spoken delivery. Explain uncertainty; do not invent sources or pretend to perform external actions.'
        )
    return (
        f'Act as a helpful {name.lower()}. Give a clear, practical response. '
        f'Explain uncertainty; do not invent sources or claim to execute actions. Ask for essential missing information.'
    )


SKILLS = [dict(id=f'skill-{i:03}', name=name, category=category,
    prompt=_make_prompt(name))
    for i, (category, name) in enumerate(((c,n) for c,names in GROUPS.items() for n in names),1)]
