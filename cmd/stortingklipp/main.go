package main

import (
	"fmt"
	"html/template"
	"net/http"
	"os"
	"os/exec"
	"stortingklipp/internal/klipp"
	"time"
)

func main() {
	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		tmpl, _ := template.ParseFiles("web/templates/index.html")
		talere, _ := klipp.HentTalerliste()
		representanter, _ := klipp.HentRepresentanter()
		regjering, _ := klipp.HentRegjering()
		
		type DisplayTaler struct {
			klipp.Taler
			Navn     string
			Parti    string
			Rolle    string
			Start    string
			Varighet string
		}

		var displayTalere []DisplayTaler
		for _, t := range talere {
			r := representanter[t.PersonID]
			reg := regjering[t.PersonID]

			role := t.Rolle
			if reg.Tittel != "" {
				role = reg.Tittel
			}

			displayTalere = append(displayTalere, DisplayTaler{
				Taler: t,
				Navn:  r.Fornavn + " " + r.Etternavn,
				Parti: r.Parti.Navn,
				Rolle: role,
			})
		}

		data := struct {
			Rom    map[string][2]string
			Talere []DisplayTaler
		}{
			Rom:    klipp.ROM,
			Talere: displayTalere,
		}
		tmpl.Execute(w, data)
	})

	http.HandleFunc("/klipp", func(w http.ResponseWriter, r *http.Request) {
		r.ParseForm()
		rom, fra, til := r.FormValue("rom"), r.FormValue("fra"), r.FormValue("til")
		if til == "" { til = "nå" }

		now := time.Now().In(klipp.OSLO)
		start, err := klipp.ParseTid(fra, now)
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		end, err := klipp.ParseTid(til, now)
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}

		mediaID := klipp.ROM[rom][0]
		masterURL, _ := klipp.MasterURL(mediaID)
		variantURL, _, _ := klipp.Variant(masterURL, 0)
		data, _ := klipp.Hent(variantURL)
		segs, _ := klipp.Segmenter(data, variantURL)
		valgt := klipp.Velg(segs, start, end)

		tmp, _ := os.CreateTemp("", "*.m3u8")
		defer os.Remove(tmp.Name())
		klipp.SkrivLokale(valgt, tmp.Name())

		out, _ := os.CreateTemp("", "*.mp4")
		defer os.Remove(out.Name())
		out.Close()

		duration := end.Sub(start).Seconds()
		
		cmd := exec.Command("ffmpeg", "-y", "-v", "error",
			"-protocol_whitelist", "file,https,tcp,tls,crypto",
			"-ss", "0",
			"-t", fmt.Sprintf("%f", duration),
			"-i", tmp.Name(),
			"-c", "copy", "-movflags", "+faststart", out.Name())

		if output, err := cmd.CombinedOutput(); err != nil {
			http.Error(w, "ffmpeg feilet: "+string(output), http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Disposition", "attachment; filename=klipp.mp4")
		http.ServeFile(w, r, out.Name())
	})

	http.ListenAndServe(":8000", nil)
}
