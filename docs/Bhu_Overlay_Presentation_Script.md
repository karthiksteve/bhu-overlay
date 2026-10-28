# Bhu-Overlay: 3–4 Minute Video Presentation Script

**Project Title:** Bhu-Overlay: An AI-Augmented Cadastral GIS Platform with Deterministic Spatial Geometry and Statutory Land Partitioning  
**Authors/Presenters:** Karthikeyan A & Vishal B  
**Affiliation:** School of Computer Science and Engineering, Vellore Institute of Technology, Chennai, India  
**Target Duration:** 3 Minutes 45 Seconds (Paced at ~130–140 words per minute)

---

## Recording Setup & Instructions

### Quickest Recording Method on Windows (No Software Needed)
1. **Windows Game Bar (Built-in HD Recorder):**
   - Press **`Win + G`** to open Xbox Game Bar, or directly press **`Win + Alt + R`** to start/stop screen recording.
   - Ensure the **Microphone icon** is unmuted (or press **`Win + Alt + M`**) so your voice is recorded clearly.
   - Recordings are automatically saved in HD MP4 to `C:\Users\speak\Videos\Captures`.

2. **Windows Snipping Tool (Alternative):**
   - Press **`Win + Shift + S`**, click the **Video camera icon**, select the browser area, enable microphone audio, and click **Record**.

3. **OBS Studio / Clipchamp:**
   - Add a *Display Capture* or *Window Capture* source set to the browser running `http://127.0.0.1:5001` or `presentation_player.html`.
   - Add an *Audio Input Capture* source set to your microphone.

---

## Timed Voice-Over Presentation Script

```
[0:00 - 0:38] PART 1: INTRODUCTION & PROBLEM CONTEXT
Visual: Dashboard initial view (OpenLayers satellite map + left administrative sidebar)
```
> "Hello everyone. Welcome to the demonstration of **Bhu-Overlay**—an AI-augmented cadastral GIS and statutory land partition engine engineered for modern rural land administration.
> 
> Across developing agrarian economies, especially in India, agricultural land fragmentation and inheritance disputes represent one of the heaviest administrative and judicial bottlenecks. The formal legal division of agricultural holdings—statutarily known as *Kurra* partition under the State Revenue Code—still relies on revenue surveyors walking fields with brass chains and drawing ocular sketches on cloth. 
> 
> This manual approach chronically produces landlocked plots, denies co-sharers access to public roads, and causes decades of civil litigation. **Bhu-Overlay** solves this by uniting official government cadastral web services, deterministic computational geometry, and statutory AI legal reasoning into a unified, transparent platform."

---

```
[0:38 - 1:18] PART 2: SYSTEM ARCHITECTURE & DATA PIPELINE
Visual: System Architecture Diagram (Fig. 1) & Location Hierarchy Cascading
```
> "Here on screen is our system architecture. Bhu-Overlay is architected into a modular, lightweight four-tier pipeline:
> 
> 1. **Client Interface:** An interactive OpenLayers web canvas supporting multiple synchronized spatial layers.
> 2. **External Data Ingestion:** A resilient reverse proxy connecting to official Bihar BhuNaksha WMS servers, ArcGIS World satellite imagery, and government road and river GIS vectors.
> 3. **Offline-First Persistence:** An embedded SQLite spatial cache that stores parcel geometries locally, ensuring instantaneous sub-100 millisecond response times even in offline rural conditions.
> 4. **Core Compute Engines:** A deterministic Shapely geometry engine for polygon bisection, paired with Google Gemini for statutory legal compliance.
> 
> Let's look at the location selector on the left. The platform provides a 7-tier cascading administrative hierarchy: selecting District Arwal, Sub-Division Arwal, Circle Kaler, Mouza Agnoor, Cadastral Survey, Map 1, and Sheet 1 dynamically streams the official cadastral sheet directly over the satellite canvas."

---

```
[1:18 - 1:58] PART 3: CADASTRAL DEMARCATION & PARCEL INSPECTION
Visual: Clicking Plot 1623 on map, boundary polygon highlights with nodes & edge lengths
```
> "Next, let's inspect an individual agricultural parcel. Clicking on **Plot 1623** triggers instantaneous reverse geocoding and vector extraction.
> 
> Notice how the platform renders the exact parcel boundary with all 43 topological vertex nodes. In real-time, the geometry engine computes and annotates the length of every single boundary segment in meters directly on the satellite map—such as 27.3 meters on the northern edge and 18.2 meters along the access corridor.
> 
> In the sidebar, comprehensive survey measurements are instantly populated: a total parcel area of **8,624.5 square meters**—equivalent to **2.131 acres**—with a perimeter of **485.2 meters**. The system automatically normalizes and repairs any self-intersecting boundary anomalies using zero-width buffer topologies."

---

```
[1:58 - 2:42] PART 4: DETERMINISTIC KURRA EQUAL PARTITION (2-WAY)
Visual: Selecting Equal Share (2 Sharers), clicking 'Generate Kurra Division', map renders 2 colored plots
```
> "Now, let us execute statutory *Kurra* land division. 
> 
> In inheritance arbitration, co-heirs are frequently entitled to equal shares. We select **Equal Share** for 2 co-sharers and click **Generate Kurra Division**.
> 
> In under **20 milliseconds**, our deterministic swept-line bisection algorithm computes the optimal transverse cut:
> - **Plot 1** is rendered in warm terracotta with exactly **4,312.13 square meters** (50.0%).
> - **Plot 2** is rendered in emerald green with **4,312.40 square meters** (50.0%).
> 
> The empirical area conservation error is under **0.001%**—vastly exceeding the statutory 0.5% tolerance threshold permitted under Revenue Manual survey guidelines. Both sub-parcels achieve a Polsby-Popper compactness score exceeding 0.68, completely preventing irregular slivers or uncultivable border strips."

---

```
[2:42 - 3:18] PART 5: STATUTORY LLM ADVISORY REASONING
Visual: Scrolling down sidebar to the AI Decision & Legal Explanation panel
```
> "What truly sets Bhu-Overlay apart is our **Statutory AI Decision Support Engine**.
> 
> Rather than relying on subjective human discretion, candidate partition geometries are submitted to Google Gemini alongside codified statutory rules:
> - **Section 116** governing co-tenure partition rights;
> - **Section 117** mandating prevention of sub-economic fragmentation; and
> - **Rule 109** requiring equitable public road frontage and shape compactness.
> 
> The AI reasoning agent validates that both sub-parcels maintain unhindered frontage along the village transport corridor, confirms soil valuation parity, and issues a formal legal justification ready for revenue court decree. In offline environments, our deterministic mathematical utility function steps in seamlessly."

---

```
[3:18 - 3:52] PART 6: CUSTOM MULTI-SHARER DIVISION & MICRO-ASSET TAGGING
Visual: Entering '50, 25, 25' in Custom Share, generating 3-way partition, placing tree/well icons
```
> "The platform also handles complex, asymmetric co-ownership. By switching to **Custom Share (%)**, we can specify unequal ratios—for instance, 50%, 25%, and 25%.
> 
> Upon generation, the multi-plane slicing engine subdivides the non-convex polygon into three contiguous, road-accessible sub-parcels with strict area adherence.
> 
> Furthermore, field surveyors can use our manual map override tools to tag immovable micro-assets—such as mature fruit trees or tube-wells. The objective function ensures that critical farm improvements are neither bisected nor monopolized by a single party."

---

```
[3:52 - 4:20] PART 7: OFFICIAL VECTOR PDF REPORT & CONCLUSION
Visual: Opening PDF modal viewer showing the Kurra survey report, highlighting GeoJSON/CSV exports
```
> "Finally, the entire approved partition is compiled into an official, court-ready **Vector PDF Kurra Survey Report**. 
> 
> As you can see in the viewer, the report embeds high-precision vector parcel drawings, co-sharer allotment tables, statutory Revenue Code decree citations, and authenticated digital signature blocks for the Tehsildar and Revenue Officer. Surveyors can also export live GeoJSON boundaries and CSV coordinates for integration into national GIS archives.
> 
> In conclusion, Bhu-Overlay transforms rural land administration from an opaque, dispute-prone manual exercise into a rapid, mathematically verifiable, and equitable digital process.
> 
> Thank you!"

---

## Screen Cue Cheat-Sheet

| Timestamp | UI Action on Screen | Spoken Key Point |
|---|---|---|
| **0:00 - 0:38** | Show full web interface, satellite basemap, header | Problem: manual chain survey disputes; Solution: Bhu-Overlay |
| **0:38 - 1:18** | Show Architecture Diagram, select District -> Mouza | 4-tier architecture, cascading 7-tier administrative selector |
| **1:18 - 1:58** | Click Plot 1623 on map, show edge lengths in meters | 43 vertices, real-time edge lengths, 8624.5 m² area conversion |
| **1:58 - 2:42** | Click 'Generate Kurra Division' (2 shares) | Sub-20ms bisection, Plot 1 & 2 at exact 50%, area error <0.001% |
| **2:42 - 3:18** | Scroll to AI Decision panel in sidebar | Gemini reasoning under Sections 116–117 and Rule 109 |
| **3:18 - 3:52** | Enter '50,25,25', generate 3-way split, tag tree/well | Arbitrary ratio support, micro-asset preservation |
| **3:52 - 4:20** | Click 'Download Segregation Report', open PDF modal | Official vector survey report, court decree, GeoJSON export |
