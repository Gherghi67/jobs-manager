import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';

import 'api.dart';
import 'models.dart';
import 'updater.dart';

void main() => runApp(const JobsApp());
const ink = Color(0xFF172C2A);
const accent = Color(0xFF146B57);
const paper = Color(0xFFF5F5EF);

class JobsApp extends StatelessWidget {
  const JobsApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Fieldwork · Jobs',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      useMaterial3: true,
      scaffoldBackgroundColor: paper,
      colorScheme: ColorScheme.fromSeed(seedColor: accent, surface: paper),
      appBarTheme: const AppBarTheme(
        backgroundColor: paper,
        foregroundColor: ink,
        centerTitle: false,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: Colors.white,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide.none,
        ),
      ),
      cardTheme: CardThemeData(
        color: Colors.white,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(22)),
      ),
    ),
    home: const JobsHome(),
  );
}

class JobsHome extends StatefulWidget {
  const JobsHome({super.key});
  @override
  State<JobsHome> createState() => _JobsHomeState();
}

class _JobsHomeState extends State<JobsHome> {
  SharedPreferences? prefs;
  Map<String, dynamic> options = defaultOptions();
  List<Job> jobs = [];
  Map<String, dynamic> saved = {};
  Set<String> dismissed = {};
  List<dynamic> sources = [];
  Map<String, dynamic>? aiStatus;
  String baseUrl = 'http://127.0.0.1:8765',
      token = '',
      status = '',
      updated = '',
      filter = '';
  String? error;
  bool loading = true, busy = false, cached = false;
  int tab = 0, generation = 0, sourceTotal = 0;
  JobsApi? activeApi;

  @override
  void initState() {
    super.initState();
    load();
  }

  @override
  void dispose() {
    generation++;
    activeApi?.close();
    super.dispose();
  }

  Future<void> load() async {
    final p = await SharedPreferences.getInstance();
    if (!mounted) {
      return;
    }
    try {
      options = {
        ...defaultOptions(),
        ...jsonDecode(p.getString('options') ?? '{}') as Map<String, dynamic>,
      };
      saved = Map<String, dynamic>.from(
        jsonDecode(p.getString('saved') ?? '{}'),
      );
      dismissed = (p.getStringList('dismissed') ?? []).toSet();
      jobs = (jsonDecode(p.getString('jobs') ?? '[]') as List)
          .map((j) => Job(Map<String, dynamic>.from(j)))
          .toList();
      sources = jsonDecode(p.getString('sources') ?? '[]') as List;
      final ai = jsonDecode(p.getString('ai') ?? 'null');
      aiStatus = ai is Map ? Map<String, dynamic>.from(ai) : null;
      cached = jobs.isNotEmpty;
    } catch (_) {
      error = 'Some saved data could not be loaded. Run a new search.';
    }
    setState(() {
      prefs = p;
      loading = false;
      baseUrl = p.getString('url') ?? baseUrl;
      token = p.getString('token') ?? '';
      updated = p.getString('updated') ?? '';
    });
  }

  // A search reports each source when it finishes, so mid-search (or after an
  // interrupted one) the run's planned total is larger than the list.
  int sourceCount() =>
      sourceTotal > sources.length ? sourceTotal : sources.length;

  Future<void> persist() async {
    final p = prefs;
    if (p == null) {
      return;
    }
    await p.setString('options', jsonEncode(options));
    await p.setString('saved', jsonEncode(saved));
    await p.setStringList('dismissed', dismissed.toList());
    await p.setString('jobs', jsonEncode(jobs.map((j) => j.data).toList()));
    await p.setString('sources', jsonEncode(sources));
    await p.setString('ai', jsonEncode(aiStatus));
    await p.setString('updated', updated);
    await p.setString('url', baseUrl);
    await p.setString('token', token);
  }

  Future<void> search() async {
    if (busy || loading) {
      return;
    }
    if (token.isEmpty) {
      await editOptions();
      return;
    }
    final run = ++generation;
    final api = JobsApi(baseUrl, token);
    activeApi = api;
    setState(() {
      busy = true;
      error = null;
      status = 'Connecting to your sources…';
    });
    try {
      final start = await api.request('/search', body: options);
      final deadline = DateTime.now().add(const Duration(minutes: 20));
      while (mounted && run == generation) {
        final result = await api.request('/search/${start['id']}');
        if (!mounted || run != generation) {
          return;
        }
        setState(() {
          final source = result['source'];
          status =
              '${source is String ? 'Fetching ${sourceName(source)}' : result['current']} · ${result['fetched']} collected';
          sources = result['sources'] as List;
          sourceTotal = (result['total'] as num?)?.toInt() ?? 0;
        });
        if (result['status'] == 'error') {
          throw Exception(result['current']);
        }
        if (result['status'] == 'complete') {
          final allFailed =
              sources.isNotEmpty &&
              sources.every((s) => s['status'] == 'error');
          if (allFailed) {
            throw Exception(
              'All sources failed. Previous results are still available. Check source status below.',
            );
          }
          setState(() {
            jobs = (result['jobs'] as List)
                .map((j) => Job(Map<String, dynamic>.from(j)))
                .toList();
            updated = result['updated_at'] as String;
            final ai = result['ai'];
            aiStatus = ai is Map ? Map<String, dynamic>.from(ai) : null;
            cached = false;
          });
          await persist();
          break;
        }
        if (DateTime.now().isAfter(deadline)) {
          throw Exception(
            'Search is taking too long. The service may still be working; try again later.',
          );
        }
        await Future<void>.delayed(const Duration(seconds: 2));
      }
    } catch (e) {
      if (mounted && run == generation) {
        setState(() {
          error =
              'Could not finish search. ${e.toString().replaceFirst('Exception: ', '')}';
        });
      }
    } finally {
      api.close();
      if (mounted && run == generation) {
        setState(() {
          busy = false;
        });
      }
    }
  }

  Future<void> editOptions() async {
    if (busy) {
      return;
    }
    final result = await Navigator.of(context).push<Map<String, dynamic>>(
      MaterialPageRoute(
        builder: (_) =>
            OptionsPage(options: options, url: baseUrl, token: token),
      ),
    );
    if (result != null && mounted) {
      setState(() {
        options = result['options'];
        baseUrl = result['url'];
        token = result['token'];
      });
      await persist();
    }
  }

  void toggleSaved(Job j) {
    setState(() {
      if (saved.containsKey(j.id)) {
        saved.remove(j.id);
      } else {
        saved[j.id] = j.data;
        dismissed.remove(j.id);
      }
    });
    unawaited(persist());
  }

  Future<void> openLink(String url) async {
    final uri = Uri.tryParse(url);
    if (uri == null || !['https', 'http'].contains(uri.scheme)) {
      return;
    }
    try {
      if (!await launchUrl(uri, mode: LaunchMode.externalApplication)) {
        throw Exception();
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Could not open the link.')),
        );
      }
    }
  }

  void detail(Job j) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (context) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: .82,
        maxChildSize: .95,
        builder: (context, controller) => ListView(
          controller: controller,
          padding: const EdgeInsets.fromLTRB(24, 0, 24, 32),
          children: [
            Text(
              j.text('company'),
              style: const TextStyle(
                color: accent,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 10),
            Text(
              j.text('title'),
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 18),
            Text('${j.text('location')} · ${j.text('type')}'),
            const SizedBox(height: 8),
            Text(eligibilityLabel(j.text('eligibility'))),
            const SizedBox(height: 8),
            const Text(
              'Location labels come from listing text. Confirm the employer can hire from Romania.',
            ),
            if (j.ai != null) ...[
              const SizedBox(height: 20),
              Text(
                "CLAUDE'S TAKE · ${j.ai!['fit']}/100 · ${verdictLabel(j.ai!['verdict'].toString())}",
                style: const TextStyle(fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              Text(romaniaLabel(j.ai!['romania'].toString())),
              ...j.aiList('reasons').map((r) => Text('+ $r')),
              ...j.aiList('concerns').map((c) => Text('− $c')),
              const SizedBox(height: 8),
              const Text(
                'Claude compared the listing text with your profile. Check the original before applying.',
              ),
            ],
            const SizedBox(height: 20),
            Text(
              'WHY IT MATCHES · ${j.text('score')} points',
              style: const TextStyle(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            Text(j.matches.join(' · ')),
            const SizedBox(height: 8),
            const Text('Keyword score, not an AI confidence estimate.'),
            const SizedBox(height: 20),
            if (j.text('salary').isNotEmpty)
              Text(j.text('salary'), style: const TextStyle(fontSize: 20)),
            const SizedBox(height: 16),
            SelectableText(j.text('description')),
            const SizedBox(height: 24),
            FilledButton.icon(
              onPressed: () => openLink(j.text('url')),
              icon: const Icon(Icons.open_in_new),
              label: const Text('Open original listing'),
            ),
            const SizedBox(height: 12),
            Text(
              'Jobs by ${j.sources.map(sourceName).join(', ')} · ${j.text('posted')}',
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final pool = tab == 1
        ? saved.values.map((j) => Job(Map<String, dynamic>.from(j))).toList()
        : jobs;
    final visible = pool
        .where(
          (j) =>
              (tab == 1 ||
                  (tab == 2
                      ? dismissed.contains(j.id)
                      : !dismissed.contains(j.id))) &&
              '${j.text('title')} ${j.text('company')} ${j.text('description')}'
                  .toLowerCase()
                  .contains(filter.toLowerCase()),
        )
        .toList();
    return Scaffold(
      appBar: AppBar(
        title: const Row(
          children: [
            Icon(Icons.work_outline_rounded, color: accent),
            SizedBox(width: 10),
            Text(
              'fieldwork',
              style: TextStyle(fontWeight: FontWeight.w800, letterSpacing: -1),
            ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: 'Search options',
            onPressed: busy || loading ? null : editOptions,
            icon: const Icon(Icons.tune_rounded),
          ),
          const SizedBox(width: 8),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: tab,
        onDestinationSelected: (v) => setState(() {
          tab = v;
        }),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.explore_outlined),
            selectedIcon: Icon(Icons.explore),
            label: 'Discover',
          ),
          NavigationDestination(
            icon: Icon(Icons.bookmark_border),
            selectedIcon: Icon(Icons.bookmark),
            label: 'Saved',
          ),
          NavigationDestination(icon: Icon(Icons.history), label: 'Dismissed'),
        ],
      ),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: search,
              child: ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
                children: [
                  Text(
                    tab == 0
                        ? 'Your next chapter.'
                        : tab == 1
                        ? 'Worth a closer look.'
                        : 'Off your shortlist.',
                    style: const TextStyle(
                      fontSize: 32,
                      fontWeight: FontWeight.w800,
                      letterSpacing: -1.3,
                      color: ink,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    tab == 0
                        ? 'Good work, on your terms.'
                        : tab == 1
                        ? 'Your saved roles stay here, even offline.'
                        : 'Restore a role whenever you change your mind.',
                    style: const TextStyle(
                      color: Color(0xFF63716D),
                      fontSize: 15,
                    ),
                  ),
                  const SizedBox(height: 24),
                  if (tab == 0) ...[
                    Container(
                      padding: const EdgeInsets.all(20),
                      decoration: BoxDecoration(
                        color: ink,
                        borderRadius: BorderRadius.circular(22),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'YOUR SEARCH',
                            style: TextStyle(
                              color: Color(0xFFAFDDBB),
                              letterSpacing: 1.8,
                              fontSize: 11,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          const SizedBox(height: 12),
                          Text(
                            options['preset'] == 'gaming'
                                ? 'Gaming & game backends'
                                : options['preset'] == 'backend'
                                ? 'Node.js · TypeScript · Backend'
                                : 'Backend · AI · Python · Go',
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 20,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          const SizedBox(height: 12),
                          Text(
                            '${options['remote_only'] ? 'Fully remote' : 'All work styles'}  /  ${options['eligibility'] == 'all'
                                ? 'All locations'
                                : options['eligibility'] == 'romania'
                                ? 'Romania eligible'
                                : 'Romania + unclear'}',
                            style: const TextStyle(color: Color(0xFFCEDBD4)),
                          ),
                          const SizedBox(height: 6),
                          Text(
                            '${options['adzuna'] ? 'Adzuna + ' : ''}${plural((options['boards'] as List).length, 'remote board')}${options['prefer_contract'] ? ' · Contracts first' : ''}${options['ai_pick'] == true ? ' · Claude picks' : ''}',
                            style: const TextStyle(color: Color(0xFFCEDBD4)),
                          ),
                          const SizedBox(height: 20),
                          SizedBox(
                            width: double.infinity,
                            child: FilledButton.icon(
                              style: FilledButton.styleFrom(
                                backgroundColor: const Color(0xFFCEF09D),
                                foregroundColor: ink,
                              ),
                              onPressed: busy ? null : search,
                              icon: Icon(
                                token.isEmpty ? Icons.link : Icons.refresh,
                              ),
                              label: Text(
                                busy
                                    ? 'Searching your sources…'
                                    : token.isEmpty
                                    ? 'Connect your job service'
                                    : 'Find opportunities',
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (busy) ...[
                      const SizedBox(height: 16),
                      const LinearProgressIndicator(),
                      const SizedBox(height: 8),
                      Text(status),
                    ],
                    if (error != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 16),
                        child: Text(
                          error!,
                          style: TextStyle(
                            color: Theme.of(context).colorScheme.error,
                          ),
                        ),
                      ),
                    if (sources.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 12),
                        child: ExpansionTile(
                          tilePadding: EdgeInsets.zero,
                          title: Text(
                            busy
                                ? '${sources.length}/${sourceCount()} sources checked'
                                : '${sources.where((s) => s['status'] != 'error').length}/${sourceCount()} sources responded',
                            style: const TextStyle(fontSize: 14),
                          ),
                          children: sources
                              .map(
                                (s) => ListTile(
                                  contentPadding: EdgeInsets.zero,
                                  leading: Icon(
                                    s['status'] == 'ok'
                                        ? Icons.check_circle_outline
                                        : Icons.info_outline,
                                    color: s['status'] == 'ok'
                                        ? accent
                                        : Colors.orange.shade800,
                                  ),
                                  title: Text(sourceName(s['name'])),
                                  subtitle: Text(
                                    s['status'] == 'error' ||
                                            s['status'] == 'partial'
                                        ? s['message'].toString()
                                        : '${plural(s['count'] as int, 'listing')}${s['cached'] == true ? ' · Cached for up to 1 hour' : ''}',
                                  ),
                                ),
                              )
                              .toList(),
                        ),
                      ),
                    if (aiStatus != null && !busy)
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Icon(
                              Icons.auto_awesome_outlined,
                              size: 18,
                              color: aiStatus!['status'] == 'error'
                                  ? Colors.orange.shade800
                                  : accent,
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                aiSummary(aiStatus!),
                                style: const TextStyle(fontSize: 13),
                              ),
                            ),
                          ],
                        ),
                      ),
                    const SizedBox(height: 20),
                  ],
                  TextField(
                    onChanged: (v) => setState(() {
                      filter = v;
                    }),
                    decoration: const InputDecoration(
                      hintText: 'Search these results',
                      prefixIcon: Icon(Icons.search),
                    ),
                  ),
                  const SizedBox(height: 20),
                  Row(
                    children: [
                      Text(switch (tab) {
                        1 => plural(visible.length, 'saved role'),
                        2 => plural(visible.length, 'dismissed role'),
                        _ => plural(
                          visible.length,
                          'opportunity',
                          'opportunities',
                        ),
                      }, style: const TextStyle(fontWeight: FontWeight.bold)),
                      const Spacer(),
                      if (cached)
                        const Text('Cached', style: TextStyle(color: accent)),
                    ],
                  ),
                  if (updated.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: Text(
                        'Last search: ${DateTime.tryParse(updated)?.toLocal().toString().split('.').first ?? updated}',
                        style: const TextStyle(
                          fontSize: 12,
                          color: Colors.black54,
                        ),
                      ),
                    ),
                  const SizedBox(height: 16),
                  if (visible.isEmpty)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 32),
                      child: Column(
                        children: [
                          Icon(
                            tab == 1
                                ? Icons.bookmarks_outlined
                                : Icons.travel_explore,
                            size: 48,
                            color: accent,
                          ),
                          const SizedBox(height: 16),
                          Text(
                            tab == 1
                                ? 'Keep the roles that catch your eye.'
                                : tab == 2
                                ? 'Nothing dismissed.'
                                : jobs.isEmpty && updated.isEmpty
                                ? 'A fresh start for your job search.'
                                : 'No roles match this view.',
                            style: const TextStyle(
                              fontSize: 17,
                              fontWeight: FontWeight.w600,
                            ),
                            textAlign: TextAlign.center,
                          ),
                          const SizedBox(height: 8),
                          Text(
                            tab == 0
                                ? 'Choose your options, then fetch from your sources.'
                                : 'Your choices are stored only on this device.',
                            textAlign: TextAlign.center,
                          ),
                        ],
                      ),
                    ),
                  ...visible.map(
                    (j) => Padding(
                      padding: const EdgeInsets.only(bottom: 14),
                      child: Card(
                        child: InkWell(
                          borderRadius: BorderRadius.circular(22),
                          onTap: () => detail(j),
                          child: Padding(
                            padding: const EdgeInsets.all(18),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    Expanded(
                                      child: Text(
                                        j.text('company'),
                                        style: const TextStyle(
                                          color: accent,
                                          fontWeight: FontWeight.w700,
                                        ),
                                      ),
                                    ),
                                    IconButton(
                                      tooltip: saved.containsKey(j.id)
                                          ? 'Unsave job'
                                          : 'Save job',
                                      visualDensity: VisualDensity.compact,
                                      onPressed: () => toggleSaved(j),
                                      icon: Icon(
                                        saved.containsKey(j.id)
                                            ? Icons.bookmark
                                            : Icons.bookmark_border,
                                        color: accent,
                                      ),
                                    ),
                                  ],
                                ),
                                Text(
                                  j.text('title'),
                                  style: const TextStyle(
                                    fontSize: 20,
                                    fontWeight: FontWeight.w700,
                                    color: ink,
                                  ),
                                ),
                                const SizedBox(height: 10),
                                Text(
                                  j.text('location'),
                                  style: const TextStyle(color: Colors.black54),
                                ),
                                const SizedBox(height: 12),
                                Wrap(
                                  spacing: 6,
                                  runSpacing: 6,
                                  children: [
                                    if (j.ai != null)
                                      pill(
                                        'Claude ${j.ai!['fit']} · ${verdictLabel(j.ai!['verdict'].toString())}',
                                        j.ai!['verdict'] == 'apply',
                                      ),
                                    pill(
                                      eligibilityLabel(j.text('eligibility')),
                                      j.eligible,
                                    ),
                                    pill(j.text('type'), false),
                                    ...j.matches
                                        .take(3)
                                        .map((m) => pill(m, false)),
                                  ],
                                ),
                                if (j.aiList('reasons').isNotEmpty)
                                  Padding(
                                    padding: const EdgeInsets.only(top: 10),
                                    child: Text(
                                      j.aiList('reasons').first,
                                      style: const TextStyle(
                                        fontSize: 13,
                                        color: Color(0xFF3F4F4B),
                                      ),
                                    ),
                                  ),
                                if (j.text('salary').isNotEmpty)
                                  Padding(
                                    padding: const EdgeInsets.only(top: 12),
                                    child: Text(
                                      j.text('salary'),
                                      style: const TextStyle(
                                        fontWeight: FontWeight.w600,
                                      ),
                                    ),
                                  ),
                                const SizedBox(height: 14),
                                Row(
                                  children: [
                                    Expanded(
                                      child: Text(
                                        'Jobs by ${j.sources.map(sourceName).join(', ')}',
                                        style: const TextStyle(
                                          fontSize: 11,
                                          color: Colors.black54,
                                        ),
                                      ),
                                    ),
                                    TextButton(
                                      onPressed: () {
                                        setState(() {
                                          if (dismissed.contains(j.id)) {
                                            dismissed.remove(j.id);
                                          } else {
                                            dismissed.add(j.id);
                                            saved.remove(j.id);
                                          }
                                        });
                                        unawaited(persist());
                                      },
                                      child: Text(
                                        tab == 2 ? 'Restore' : 'Dismiss',
                                      ),
                                    ),
                                  ],
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
    );
  }

  Widget pill(String text, bool green) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
    decoration: BoxDecoration(
      color: green ? const Color(0xFFE8F1DA) : paper,
      borderRadius: BorderRadius.circular(8),
    ),
    child: Text(
      text,
      style: TextStyle(fontSize: 11, color: green ? accent : ink),
    ),
  );
}

class OptionsPage extends StatefulWidget {
  final Map<String, dynamic> options;
  final String url, token;
  const OptionsPage({
    super.key,
    required this.options,
    required this.url,
    required this.token,
  });
  @override
  State<OptionsPage> createState() => _OptionsPageState();
}

class _OptionsPageState extends State<OptionsPage> {
  late Map<String, dynamic> o;
  late TextEditingController url, token, keywords;
  String? connection, updateMessage;
  Map<String, dynamic>? installed, release;
  double? progress;
  bool checking = false, updating = false;
  @override
  void initState() {
    super.initState();
    o = jsonDecode(jsonEncode(widget.options));
    url = TextEditingController(text: widget.url);
    token = TextEditingController(text: widget.token);
    keywords = TextEditingController(text: o['keywords']);
    AppUpdater.onInstallFailed((message) {
      if (mounted) {
        setState(() {
          updateMessage = message;
        });
      }
    });
    unawaited(loadInstalled());
  }

  @override
  void dispose() {
    AppUpdater.channel.setMethodCallHandler(null);
    url.dispose();
    token.dispose();
    keywords.dispose();
    super.dispose();
  }

  Future<void> check() async {
    setState(() {
      checking = true;
      connection = null;
    });
    final api = JobsApi(url.text.trim(), token.text.trim());
    try {
      final health = await api.request('/health');
      final adzuna = health['adzuna_configured'] == true
          ? 'Connected. Adzuna credentials are ready.'
          : 'Connected. Remote boards ready; Adzuna needs credentials on the service.';
      final claude = switch (health['claude_available']) {
        true => ' Claude ranking is ready.',
        false => ' Claude Code was not found on the service.',
        _ => '',
      };
      if (mounted) {
        setState(() {
          connection = '$adzuna$claude';
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          connection = 'Connection failed. Check the URL, access token, and that the service is running.';
        });
      }
    } finally {
      api.close();
      if (mounted) {
        setState(() {
          checking = false;
        });
      }
    }
  }

  Future<void> loadInstalled() async {
    try {
      final info = await AppUpdater.info();
      if (mounted) {
        setState(() {
          installed = info;
        });
      }
    } on MissingPluginException {
      // Only the Android app has the installer channel.
    }
  }

  Future<void> checkUpdate() async {
    final local = installed;
    if (local == null) {
      setState(() {
        updateMessage = 'App updates work in the Android app only.';
      });
      return;
    }
    setState(() {
      updating = true;
      updateMessage = null;
    });
    final api = JobsApi(url.text.trim(), token.text.trim());
    try {
      final latest = await api.request('/app');
      if (mounted) {
        setState(() {
          if (latest['available'] != true) {
            updateMessage = 'Your service has no app build yet. Run scripts/build_apk.sh on your computer.';
          } else if (isNewer(local, latest)) {
            release = latest;
            updateMessage = 'Build ${latest['version_code']} is ready.';
          } else {
            updateMessage = 'You have the latest build.';
          }
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          updateMessage = e.toString().replaceFirst('Exception: ', '');
        });
      }
    } finally {
      api.close();
      if (mounted) {
        setState(() {
          updating = false;
        });
      }
    }
  }

  Future<void> installUpdate() async {
    final latest = release!;
    setState(() {
      updating = true;
      updateMessage = null;
    });
    final api = JobsApi(url.text.trim(), token.text.trim());
    try {
      final local = await AppUpdater.info();
      if (local['canInstall'] != true) {
        setState(() {
          updateMessage = 'Allow Fieldwork to install apps, then come back and tap Install again.';
        });
        await AppUpdater.openInstallSettings();
        return;
      }
      setState(() {
        progress = 0;
      });
      final file = File('${local['cacheDir']}/fieldwork-update.apk');
      await api.download(
        '/app/fieldwork.apk',
        file,
        onProgress: (received, total) {
          if (mounted && total > 0) {
            setState(() {
              progress = received / total;
            });
          }
        },
      );
      if (await file.length() != latest['size']) {
        throw Exception('The download was incomplete. Try again.');
      }
      if (mounted) {
        setState(() {
          progress = null;
          updateMessage = 'Checking the download…';
        });
      }
      await AppUpdater.install(file.path, latest['sha256'] as String);
      if (mounted) {
        setState(() {
          updateMessage = 'Confirm the update in the Android dialog, then open Fieldwork again.';
        });
      }
    } on PlatformException catch (e) {
      if (mounted) {
        setState(() {
          updateMessage = e.message ?? 'The update could not be installed.';
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          updateMessage = e.toString().replaceFirst('Exception: ', '');
        });
      }
    } finally {
      api.close();
      if (mounted) {
        setState(() {
          updating = false;
          progress = null;
        });
      }
    }
  }

  void save() {
    if (!JobsApi.validUrl(url.text) || token.text.trim().isEmpty) {
      setState(() {
        connection = 'Enter a valid service URL and access token.';
      });
      return;
    }
    if (!(o['adzuna'] as bool) && (o['boards'] as List).isEmpty) {
      setState(() {
        connection = 'Enable at least one job source.';
      });
      return;
    }
    if ((o['countries'] as List).isEmpty) {
      setState(() {
        connection = 'Select at least one Adzuna search country.';
      });
      return;
    }
    o['keywords'] = keywords.text.trim();
    Navigator.pop(context, {
      'options': o,
      'url': url.text.trim(),
      'token': token.text.trim(),
    });
  }

  Widget heading(String text) => Padding(
    padding: const EdgeInsets.only(top: 28, bottom: 12),
    child: Text(
      text,
      style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
    ),
  );
  Widget toggle(String key, String title, String subtitle) => SwitchListTile(
    contentPadding: EdgeInsets.zero,
    title: Text(title),
    subtitle: Text(subtitle),
    value: o[key] as bool,
    onChanged: (v) => setState(() {
      o[key] = v;
    }),
  );
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Your search options')),
    bottomNavigationBar: SafeArea(
      minimum: const EdgeInsets.all(16),
      child: FilledButton(onPressed: save, child: const Text('Save options')),
    ),
    body: ListView(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 30),
      children: [
        heading('Find your kind of work'),
        DropdownButtonFormField<String>(
          initialValue: o['preset'],
          decoration: const InputDecoration(labelText: 'Role focus'),
          items: const [
            DropdownMenuItem(
              value: 'backend',
              child: Text('Node.js / TypeScript backend'),
            ),
            DropdownMenuItem(
              value: 'broad',
              child: Text('Backend + AI + Python / Go'),
            ),
            DropdownMenuItem(
              value: 'gaming',
              child: Text('Gaming industry + studio boards'),
            ),
          ],
          onChanged: (v) => setState(() {
            o['preset'] = v!;
          }),
        ),
        const SizedBox(height: 16),
        TextField(
          controller: keywords,
          maxLength: 200,
          decoration: const InputDecoration(
            labelText: 'Custom skills (optional)',
            hintText: 'TypeScript, NestJS, LLM',
            helperText: 'Comma separated. Replaces the preset’s core skills.',
          ),
        ),
        toggle(
          'remote_only',
          'Fully remote only',
          'Exclude hybrid, on-site, and unknown work styles.',
        ),
        toggle(
          'prefer_contract',
          'Put contracts first',
          'Rank confirmed and likely contracts above full-time roles.',
        ),
        toggle(
          'contract_only',
          'Confirmed contracts only',
          'Hide full-time, unknown, and unconfirmed contract roles.',
        ),
        const SizedBox(height: 16),
        DropdownButtonFormField<String>(
          initialValue: o['eligibility'],
          decoration: const InputDecoration(labelText: 'Hiring eligibility'),
          items: const [
            DropdownMenuItem(
              value: 'romania',
              child: Text('Romania / Europe / Worldwide'),
            ),
            DropdownMenuItem(
              value: 'romania_unclear',
              child: Text('Include unclear eligibility'),
            ),
            DropdownMenuItem(
              value: 'all',
              child: Text('All, including US-only roles'),
            ),
          ],
          onChanged: (v) => setState(() {
            o['eligibility'] = v!;
          }),
        ),
        const SizedBox(height: 16),
        Text('Posted within ${o['max_age_days']} days'),
        Slider(
          value: (o['max_age_days'] as num).toDouble(),
          min: 1,
          max: 90,
          divisions: 89,
          label: '${o['max_age_days']} days',
          onChanged: (v) => setState(() {
            o['max_age_days'] = v.round();
          }),
        ),
        const Text(
          'Studio boards list open roles and are not filtered by posting age.',
          style: TextStyle(fontSize: 12, color: Colors.black54),
        ),
        heading('Ranking'),
        toggle(
          'ai_pick',
          'Let Claude rank the top roles',
          'Claude Code on your computer scores up to 40 roles against your profile, using your Claude subscription.',
        ),
        heading('Job sources'),
        toggle(
          'adzuna',
          'Adzuna',
          'Uses the credentials configured on your service.',
        ),
        const Text(
          'Adzuna search markets (not your eligibility):',
          style: TextStyle(fontSize: 13),
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          children:
              {
                    'us': 'US',
                    'gb': 'UK',
                    'de': 'Germany',
                    'nl': 'Netherlands',
                    'pl': 'Poland',
                    'at': 'Austria',
                    'es': 'Spain',
                    'fr': 'France',
                  }.entries
                  .map(
                    (e) => FilterChip(
                      label: Text(e.value),
                      selected: (o['countries'] as List).contains(e.key),
                      onSelected: (v) => setState(() {
                        final countries = o['countries'] as List;
                        if (v && countries.length < 7) {
                          countries.add(e.key);
                        } else if (!v) {
                          countries.remove(e.key);
                        }
                      }),
                    ),
                  )
                  .toList(),
        ),
        const SizedBox(height: 12),
        ...boardNames.entries.map(
          (e) => CheckboxListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(e.value),
            value: (o['boards'] as List).contains(e.key),
            onChanged: (v) => setState(() {
              final list = o['boards'] as List;
              v! ? list.add(e.key) : list.remove(e.key);
            }),
          ),
        ),
        const Text(
          'The gaming preset also searches the studio boards from cv-refactor when remote boards are enabled.',
        ),
        heading('Connect your service'),
        const Text(
          'Run scripts/serve.sh on your computer. For a USB-connected Android phone, run adb reverse tcp:8765 tcp:8765 and use the address below. For a hosted service, use its HTTPS address.',
        ),
        const SizedBox(height: 16),
        TextField(
          controller: url,
          keyboardType: TextInputType.url,
          autocorrect: false,
          decoration: const InputDecoration(
            labelText: 'Service URL',
            hintText: 'http://127.0.0.1:8765',
          ),
        ),
        const SizedBox(height: 16),
        TextField(
          controller: token,
          obscureText: true,
          autocorrect: false,
          enableSuggestions: false,
          decoration: const InputDecoration(
            labelText: 'Service access token',
            helperText: 'From backend/.access-token. Not your Adzuna key.',
          ),
        ),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: checking ? null : check,
          icon: const Icon(Icons.link),
          label: Text(checking ? 'Connecting…' : 'Test connection'),
        ),
        if (connection != null)
          Padding(
            padding: const EdgeInsets.only(top: 10),
            child: Text(connection!),
          ),
        heading('App updates'),
        Text(
          installed == null
              ? 'Installs builds that your computer publishes with scripts/build_apk.sh.'
              : '${buildLabel(installed!)}. Updates come from the service above.',
        ),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: updating
              ? null
              : release == null
              ? checkUpdate
              : installUpdate,
          icon: Icon(
            release == null
                ? Icons.system_update_outlined
                : Icons.download_rounded,
          ),
          label: Text(
            updating
                ? progress != null
                      ? 'Downloading…'
                      : 'Working…'
                : release == null
                ? 'Check for app update'
                : 'Install build ${release!['version_code']}',
          ),
        ),
        if (progress != null)
          Padding(
            padding: const EdgeInsets.only(top: 10),
            child: LinearProgressIndicator(value: progress),
          ),
        if (updateMessage != null)
          Padding(
            padding: const EdgeInsets.only(top: 10),
            child: Text(updateMessage!),
          ),
        const SizedBox(height: 12),
        const Text(
          'Saved jobs, dismissed jobs, options, and cached results stay on this device. No applications are submitted automatically.',
          style: TextStyle(fontSize: 12, color: Colors.black54),
        ),
      ],
    ),
  );
}
