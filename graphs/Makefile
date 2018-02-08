
all: releases.png

releases.tsv: process.py
	python process.py

releases.png: releases.tsv
	Rscript charts.R

.PHONY: clean all
clean:
	rm -f releases.png releases.tsv releases_supported.png releases_supported.tsv
