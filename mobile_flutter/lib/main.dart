// RoadScan AI - Flutter mobile app
// Calls the same Flask /detect endpoint as the web app.
//
// SETUP:
// 1. flutter create roadscan_ai   (then replace lib/main.dart with this file)
// 2. Add to pubspec.yaml dependencies: http, image_picker
// 3. Set SERVER_URL below to your deployed Flask server (or your PC's LAN IP for local testing)
// 4. flutter run  (or build apk/ipa for real device)

import 'dart:convert';
import 'dart:io';
import 'dart:async';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:image_picker/image_picker.dart';

const String SERVER_URL = "http://127.0.0.1:5000";

void main() => runApp(const RoadScanApp());

class RoadScanApp extends StatelessWidget {
  const RoadScanApp({super.key});
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'RoadScan AI',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF1C1E22),
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFFFF5A1F),
          brightness: Brightness.dark,
        ),
        fontFamily: 'Inter',
        appBarTheme: const AppBarTheme(
          elevation: 0,
          centerTitle: false,
          titleSpacing: 20,
        ),
      ),
      home: const DetectorScreen(),
    );
  }
}

class Detection {
  final String cls;
  final double confidence;
  final String severity;
  Detection({required this.cls, required this.confidence, required this.severity});
  factory Detection.fromJson(Map<String, dynamic> j) => Detection(
        cls: j['class'],
        confidence: (j['confidence'] as num).toDouble(),
        severity: j['severity'],
      );
}

class DetectorScreen extends StatefulWidget {
  const DetectorScreen({super.key});
  @override
  State<DetectorScreen> createState() => _DetectorScreenState();
}

class _DetectorScreenState extends State<DetectorScreen> {
  File? _imageFile;
  String? _resultImageUrl;
  List<Detection> _detections = [];
  bool _loading = false;
  String _status = "";
  List<Map<String, dynamic>> _updates = [];
  Timer? _updatesTimer;

  final _picker = ImagePicker();

  @override
  void initState() {
    super.initState();
    _loadUpdates();
    _updatesTimer = Timer.periodic(const Duration(seconds: 10), (_) => _loadUpdates());
  }

  @override
  void dispose() {
    _updatesTimer?.cancel();
    super.dispose();
  }

  Future<void> _loadUpdates() async {
    try {
      final response = await http.get(Uri.parse("$SERVER_URL/api/updates"));
      if (response.statusCode != 200 || !mounted) return;
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      setState(() {
        _updates = (data['updates'] as List)
            .map((item) => Map<String, dynamic>.from(item as Map))
            .toList();
      });
    } catch (_) {
      // The detector remains usable if the optional live feed is unavailable.
    }
  }

  Future<void> _pickImage(ImageSource source) async {
    final picked = await _picker.pickImage(source: source, imageQuality: 85);
    if (picked == null) return;
    setState(() {
      _imageFile = File(picked.path);
      _resultImageUrl = null;
      _detections = [];
      _status = "";
    });
  }

  Future<void> _runDetection() async {
    if (_imageFile == null) return;
    setState(() {
      _loading = true;
      _status = "Running detection...";
    });

    try {
      final uri = Uri.parse("$SERVER_URL/detect");
      final request = http.MultipartRequest("POST", uri);
      request.files.add(await http.MultipartFile.fromPath("image", _imageFile!.path));
      final streamed = await request.send();
      final response = await http.Response.fromStream(streamed);

      if (response.statusCode != 200) {
        setState(() => _status = "Server error: ${response.statusCode}");
        return;
      }

      final data = jsonDecode(response.body);
      if (data['error'] != null) {
        setState(() => _status = "Error: ${data['error']}");
        return;
      }

      final dets = (data['detections'] as List).map((d) => Detection.fromJson(d)).toList();
      setState(() {
        _detections = dets;
        _resultImageUrl = "$SERVER_URL${data['result_image']}";
        _status = "Found ${data['count']} damage instance(s).";
      });
      await _loadUpdates();
    } catch (e) {
      setState(() => _status = "Request failed: $e");
    } finally {
      setState(() => _loading = false);
    }
  }

  Color _severityColor(String sev) {
    switch (sev) {
      case "High":
        return const Color(0xFFE6432F);
      case "Medium":
        return const Color(0xFFF5B400);
      default:
        return const Color(0xFF5FBF8F);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: Row(
          children: const [
            Icon(Icons.change_history, color: Color(0xFFFF6A3D), size: 20),
            SizedBox(width: 8),
            Text("RoadScan AI", style: TextStyle(fontWeight: FontWeight.bold, letterSpacing: 1.2)),
          ],
        ),
      ),
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              Color(0xFF0F172A),
              Color(0xFF111827),
              Color(0xFF1F2937),
            ],
          ),
        ),
        child: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 28),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(22),
                    gradient: const LinearGradient(
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                      colors: [
                        Color(0xFFFF7A1A),
                        Color(0xFFF15A24),
                        Color(0xFFB93D18),
                      ],
                    ),
                    boxShadow: [
                      BoxShadow(
                        color: const Color(0xFFFF6A3D).withOpacity(0.35),
                        blurRadius: 18,
                        offset: const Offset(0, 12),
                      ),
                    ],
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        "Smart road inspection",
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          letterSpacing: 1.5,
                          color: Color(0xFFFFE8D9),
                        ),
                      ),
                      const SizedBox(height: 10),
                      const Text(
                        "Damage Detector",
                        style: TextStyle(
                          fontSize: 28,
                          fontWeight: FontWeight.w900,
                          color: Colors.white,
                        ),
                      ),
                      const SizedBox(height: 8),
                      const Text(
                        "Capture or upload a road photo to detect cracks, potholes, and surface damage instantly.",
                        style: TextStyle(
                          color: Color(0xFFFFE8D9),
                          fontSize: 14,
                          height: 1.5,
                        ),
                      ),
                      const SizedBox(height: 18),
                      Row(
                        children: [
                          _statusPill(Icons.bolt, "AI-powered", const Color(0xFFFFF0E6)),
                          const SizedBox(width: 8),
                          _statusPill(Icons.speed, "Fast scan", const Color(0xFFFFD166)),
                        ],
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 20),

                GestureDetector(
                  onTap: () => _showSourceSheet(context),
                  child: Container(
                    height: 270,
                    width: double.infinity,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(24),
                      border: Border.all(color: const Color(0xFF3B4658), width: 1.2),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withOpacity(0.25),
                          blurRadius: 18,
                          offset: const Offset(0, 10),
                        ),
                      ],
                    ),
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(24),
                      child: _resultImageUrl != null
                          ? Image.network(_resultImageUrl!, fit: BoxFit.cover)
                          : _imageFile != null
                              ? Image.file(_imageFile!, fit: BoxFit.cover)
                              : Container(
                                  decoration: const BoxDecoration(
                                    gradient: LinearGradient(
                                      begin: Alignment.topCenter,
                                      end: Alignment.bottomCenter,
                                      colors: [
                                        Color(0xFF1E293B),
                                        Color(0xFF111827),
                                      ],
                                    ),
                                  ),
                                  child: const Center(
                                    child: Column(
                                      mainAxisAlignment: MainAxisAlignment.center,
                                      children: [
                                        Icon(Icons.add_a_photo_outlined,
                                            color: Color(0xFFFF8A50), size: 48),
                                        SizedBox(height: 12),
                                        Text(
                                          "Tap to add a road photo",
                                          style: TextStyle(
                                            fontSize: 18,
                                            fontWeight: FontWeight.w700,
                                            color: Colors.white,
                                          ),
                                        ),
                                        SizedBox(height: 6),
                                        Text(
                                          "Camera or gallery",
                                          style: TextStyle(color: Colors.grey, fontSize: 13),
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                    ),
                  ),
                ),
                const SizedBox(height: 18),

                Container(
                  width: double.infinity,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(18),
                    gradient: const LinearGradient(
                      begin: Alignment.centerLeft,
                      end: Alignment.centerRight,
                      colors: [
                        Color(0xFFFF6A3D),
                        Color(0xFFFF8A50),
                      ],
                    ),
                    boxShadow: [
                      BoxShadow(
                        color: const Color(0xFFFF6A3D).withOpacity(0.35),
                        blurRadius: 15,
                        offset: const Offset(0, 8),
                      ),
                    ],
                  ),
                  child: ElevatedButton(
                    onPressed: (_imageFile == null || _loading) ? null : _runDetection,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.transparent,
                      foregroundColor: Colors.white,
                      shadowColor: Colors.transparent,
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
                    ),
                    child: _loading
                        ? const SizedBox(
                            height: 20,
                            width: 20,
                            child: CircularProgressIndicator(strokeWidth: 2.5, color: Colors.white),
                          )
                        : const Text(
                            "RUN DETECTION",
                            style: TextStyle(fontWeight: FontWeight.w800, letterSpacing: 1.2),
                          ),
                  ),
                ),

                if (_status.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                    decoration: BoxDecoration(
                      color: const Color(0xFF1F2937).withOpacity(0.8),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: const Color(0xFF374151)),
                    ),
                    child: Text(
                      _status,
                      style: const TextStyle(color: Color(0xFFE5E7EB), fontSize: 13),
                    ),
                  ),
                ],

                if (_detections.isNotEmpty) ...[
                  const SizedBox(height: 20),
                  const Text(
                    "Results",
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: Colors.white),
                  ),
                  const SizedBox(height: 10),
                  ..._detections.map((d) => Container(
                        margin: const EdgeInsets.only(bottom: 10),
                        decoration: BoxDecoration(
                          color: const Color(0xFF1F2937),
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(color: const Color(0xFF374151)),
                        ),
                        child: ListTile(
                          contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                          leading: Container(
                            width: 42,
                            height: 42,
                            decoration: BoxDecoration(
                              color: _severityColor(d.severity).withOpacity(0.18),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Icon(
                              Icons.warning_amber_rounded,
                              color: _severityColor(d.severity),
                              size: 22,
                            ),
                          ),
                          title: Text(
                            d.cls,
                            style: const TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          subtitle: Text(
                            "Confidence: ${(d.confidence * 100).toStringAsFixed(0)}%",
                            style: const TextStyle(color: Color(0xFFCBD5E1)),
                          ),
                          trailing: Text(
                            d.severity,
                            style: TextStyle(
                              color: _severityColor(d.severity),
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                        ),
                      )),
                ],

                        const SizedBox(height: 22),
                        _buildLiveUpdates(),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _statusPill(IconData icon, String label, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.14),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: Colors.white.withOpacity(0.18)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 15, color: color),
          const SizedBox(width: 6),
          Text(
            label,
            style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w700),
          ),
        ],
      ),
    );
  }

  Widget _buildLiveUpdates() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF111827),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFF374151)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.sensors, color: Color(0xFFFF8A50), size: 21),
              const SizedBox(width: 8),
              const Expanded(
                child: Text(
                  "Live safety updates",
                  style: TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w800),
                ),
              ),
              Text(
                "LIVE",
                style: TextStyle(color: const Color(0xFF5FBF8F), fontSize: 11, fontWeight: FontWeight.w800),
              ),
            ],
          ),
          const SizedBox(height: 6),
          const Text(
            "New pothole and emergency hazards appear here after scans.",
            style: TextStyle(color: Color(0xFF94A3B8), fontSize: 12, height: 1.4),
          ),
          const SizedBox(height: 12),
          if (_updates.isEmpty)
            const Text(
              "No incidents reported yet. Run a detection to publish the first update.",
              style: TextStyle(color: Color(0xFFCBD5E1), fontSize: 13),
            )
          else
            ..._updates.take(5).map((update) {
              final urgent = update['urgent'] == true;
              final color = urgent ? const Color(0xFFE6432F) : const Color(0xFFF5B400);
              return Container(
                margin: const EdgeInsets.only(bottom: 8),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: const Color(0xFF1F2937),
                  borderRadius: BorderRadius.circular(12),
                  border: Border(left: BorderSide(color: color, width: 3)),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(urgent ? Icons.emergency : Icons.warning_amber_rounded, color: color, size: 20),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            "${urgent ? 'EMERGENCY' : update['severity']} · ${update['class']}",
                            style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w800),
                          ),
                          const SizedBox(height: 3),
                          Text(update['message'] ?? 'Road damage reported.', style: const TextStyle(color: Colors.white, fontSize: 12)),
                        ],
                      ),
                    ),
                  ],
                ),
              );
            }),
        ],
      ),
    );
  }

  void _showSourceSheet(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF1F2937),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => SafeArea(
        child: Wrap(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 18, 16, 8),
              child: const Text(
                "Select image source",
                style: TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.w700,
                  fontSize: 18,
                ),
              ),
            ),
            ListTile(
              leading: const Icon(Icons.camera_alt_outlined, color: Color(0xFFFF8A50)),
              title: const Text("Take a photo", style: TextStyle(color: Colors.white)),
              onTap: () {
                Navigator.pop(ctx);
                _pickImage(ImageSource.camera);
              },
            ),
            ListTile(
              leading: const Icon(Icons.photo_library_outlined, color: Color(0xFFFF8A50)),
              title: const Text("Choose from gallery", style: TextStyle(color: Colors.white)),
              onTap: () {
                Navigator.pop(ctx);
                _pickImage(ImageSource.gallery);
              },
            ),
          ],
        ),
      ),
    );
  }
}
