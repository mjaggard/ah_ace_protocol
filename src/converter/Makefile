ah_converter: converter.o
	$(CXX) $(LDFLAGS) converter.o -o ah_converter $(LIBS)
converter.o: converter.cpp
	$(CXX) $(CXXFLAGS) -c converter.cpp

clean:
	rm *.o ah_converter
