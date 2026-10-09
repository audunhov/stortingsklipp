package main

import (
	"html/template"
	"net/http"
)

type taler struct {
	PersonID string
	Navn     string
	Parti    string
	Rolle    string
	Start    string
	Varighet string
}

var talere = []taler{
	{"MASG", "Masud Gharahkhani", "Arbeiderpartiet", "President", "09:00", "3:00"},
	{"JGS", "Jonas Gahr Støre", "Arbeiderpartiet", "Statsminister", "09:03", "10:00"},
	{"JANVES", "Jan Christian Vestre", "Arbeiderpartiet", "Helse- og omsorgsminister", "09:13", "7:00"},
	{"SYL", "Sylvi Listhaug", "Fremskrittspartiet", "Representant", "09:20", "9:00"},
	{"ES", "Erna Solberg", "Høyre", "Representant", "09:29", "8:00"},
	{"MARMAR", "Marie Sneve Martinussen", "Rødt", "Representant", "09:37", "7:00"},
	{"GKAL", "Grunde Almeland", "Venstre", "Representant", "09:44", "7:00"},
	{"HNJ", "Helge André Njåstad", "Fremskrittspartiet", "Representant", "09:51", "8:00"},
	{"UAB", "Une Bastholm", "Miljøpartiet De Grønne", "Representant", "09:59", "7:00"},
	{"TMV", "Trygve Slagsvold Vedum", "Senterpartiet", "Representant", "10:06", "11:00"},
	{"KAMGUN", "Kamzy Gunaratnam", "Arbeiderpartiet", "Samferdselsminister", "10:17", "6:00"},
	{"BJMO", "Bjørnar Moxnes", "Rødt", "Representant", "10:23", "5:00"},
}

var rom = map[string][2]string{
	"arrangement": {"", "Arrangementer"},
	"hoering1":    {"", "Høringssal 1"},
	"hoering2":    {"", "Høringssal 2"},
	"n202":        {"", "Høringssal N-202"},
	"sal":         {"", "Stortingssalen"},
}

func main() {
	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		tmpl, err := template.ParseFiles("web/templates/index.html")
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		tmpl.Execute(w, struct {
			Rom    map[string][2]string
			Talere []taler
		}{rom, talere})
	})
	http.HandleFunc("/klipp", func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "klipp er ikke tilgjengelig i mock-modus", http.StatusNotImplemented)
	})
	http.ListenAndServe(":8001", nil)
}
